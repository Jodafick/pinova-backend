"""
Libellés de topics dynamiques : cache JSON (TopicTranslation) + googletrans.

Le nom canonique est `Topic.name` (clé métier). Les traductions sont stockées dans
TopicTranslation.translations par code langue (fr, en, es, …).
"""
from __future__ import annotations

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
            translations[lang] = async_to_sync(translate_text_to)(t_inst, canonical_name, lang)
            record.translations = translations
            record.save(update_fields=['translations', 'updated_at'])
        except RuntimeError:
            pass

    if lang == 'fr':
        display = translations.get('fr', canonical_name)
    else:
        display = translations.get(lang, canonical_name)

    return display, translations
