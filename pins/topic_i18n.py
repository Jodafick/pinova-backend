"""
Libellés de topics dynamiques : cache JSON (TopicTranslation) + googletrans.

Le nom canonique est `Topic.name` (clé métier). Les traductions sont stockées dans
TopicTranslation.translations par code langue (fr, en, es, …).
"""
from __future__ import annotations

import asyncio

from googletrans import Translator
from asgiref.sync import async_to_sync

from .models import TopicTranslation
from .translation import translate_text_to

# Aligné sur l’endpoint topics/ (googletrans + locales app)
SUPPORTED_TOPIC_LANGS = frozenset({'fr', 'en', 'es', 'de', 'it', 'pt', 'ar', 'ja', 'zh', 'fon'})


def resolve_topic_language(request) -> str:
    """Priorité : ?lang= → Accept-Language → profil utilisateur → fr."""
    if not request:
        return 'fr'
    qp = (request.query_params.get('lang') or '').strip().lower()
    if qp:
        return qp.split('-')[0]
    accept = request.headers.get('Accept-Language') or ''
    if accept:
        primary = accept.split(',')[0].split(';')[0].strip().lower().split('-')[0]
        if primary in SUPPORTED_TOPIC_LANGS:
            return primary
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return (user.profile.preferred_language or 'fr').strip().lower().split('-')[0]
    return 'fr'


def ensure_topic_translation(
    canonical_name: str,
    lang: str,
    *,
    translator: Translator | None = None,
) -> tuple[str, dict]:
    """
    Retourne (libellé affiché pour `lang`, dict translations complet).
    Crée ou met à jour TopicTranslation si une traduction manque encore.
    """
    if not canonical_name or not str(canonical_name).strip():
        return '', {}

    lang = (lang or 'fr').strip().lower().split('-')[0]
    if lang not in SUPPORTED_TOPIC_LANGS:
        lang = 'fr'

    record, _ = TopicTranslation.objects.get_or_create(
        topic=canonical_name,
        defaults={'translations': {'fr': canonical_name}},
    )
    translations = dict(record.translations or {})
    if 'fr' not in translations:
        translations['fr'] = canonical_name

    if lang != 'fr' and lang not in translations:
        t_inst = translator or Translator()
        try:
            translations[lang] = async_to_sync(translate_text_to)(t_inst, canonical_name, lang, 'fr')
            record.translations = translations
            record.save(update_fields=['translations', 'updated_at'])
        except RuntimeError:
            pass

    if lang == 'fr':
        display = translations.get('fr', canonical_name)
    else:
        display = translations.get(lang, canonical_name)

    return display, translations


async def _warm_topic_translations_async(canonical_name: str) -> None:
    """À l’appui d’un nouveau Topic : préremplit toutes les langues supportées."""
    if not canonical_name or not str(canonical_name).strip():
        return

    record, _ = TopicTranslation.objects.get_or_create(
        topic=canonical_name,
        defaults={'translations': {'fr': canonical_name}},
    )
    translations = dict(record.translations or {})
    translations.setdefault('fr', canonical_name)

    t_inst = Translator()

    async def ensure_lang(lang_code: str) -> None:
        if lang_code == 'fr':
            return
        if lang_code not in SUPPORTED_TOPIC_LANGS:
            return
        if translations.get(lang_code):
            return
        try:
            translations[lang_code] = await translate_text_to(t_inst, canonical_name, lang_code, 'fr')
        except (RuntimeError, Exception):
            pass

    await asyncio.gather(*[ensure_lang(lc) for lc in sorted(SUPPORTED_TOPIC_LANGS)])

    record.translations = translations
    record.save(update_fields=['translations', 'updated_at'])


def warm_topic_translations_for_new_topic(canonical_name: str) -> None:
    """Version synchrone pour Serializer / signaux Django."""
    try:
        async_to_sync(_warm_topic_translations_async)(canonical_name)
    except RuntimeError:
        pass
