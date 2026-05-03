"""
Pages légales + contact : contenu issu du modèle LegalDocument, avec traductions
googletrans (cache EN dans les champs title_en/body_en, autres langues dans translations_cache).
"""

from __future__ import annotations

import asyncio
import copy
import logging
from typing import Any

from asgiref.sync import async_to_sync
from googletrans import Translator

from .legal_defaults import default_body, default_title
from .models import LegalDocument
from .translation import translate_text_to

logger = logging.getLogger(__name__)

SUPPORTED_LEGAL_LANGS = frozenset({'fr', 'en', 'es', 'de', 'it', 'pt', 'ar', 'ja', 'zh', 'fon'})

_MAX_CHUNK = 4000


def normalize_legal_lang(raw: str | None) -> str:
    lang = (raw or 'fr').strip().lower().split('-')[0]
    if lang not in SUPPORTED_LEGAL_LANGS:
        return 'fr'
    return lang


def googletrans_dest(lang: str) -> str:
    if lang == 'zh':
        return 'zh-cn'
    return lang


async def _translate_long_text_async(translator: Translator, text: str, dest_lang: str) -> str:
    """Découpe le texte pour éviter les limites de googletrans."""
    if not text or not text.strip():
        return text
    dest = googletrans_dest(dest_lang)
    blocks = [b.strip() for b in text.split('\n\n') if b.strip()]
    if not blocks:
        return await translate_text_to(translator, text.strip(), dest, 'fr')

    async def one(block: str) -> str:
        if len(block) <= _MAX_CHUNK:
            return await translate_text_to(translator, block, dest, 'fr')
        pieces: list[str] = []
        rest = block
        while rest:
            chunk = rest[:_MAX_CHUNK]
            cut = chunk.rfind('\n')
            if len(rest) > _MAX_CHUNK and cut > 800:
                chunk = rest[: cut + 1]
            pieces.append(await translate_text_to(translator, chunk.strip(), dest, 'fr'))
            rest = rest[len(chunk) :].strip()
        return '\n'.join(pieces)

    parts = await asyncio.gather(*[one(b) for b in blocks])
    return '\n\n'.join(parts)


def translate_long_text_sync(text: str, dest_lang: str) -> str:
    translator = Translator()
    return async_to_sync(_translate_long_text_async)(translator, text, dest_lang)


def _canonical_fr(doc: LegalDocument | None, slug: str) -> tuple[str, str]:
    t = ((doc.title_fr if doc else '') or '').strip() or default_title(slug, 'fr')
    b = ((doc.body_fr if doc else '') or '').strip() or default_body(slug, 'fr')
    return t, b


def _resolve_en(doc: LegalDocument | None, slug: str, title_fr: str, body_fr: str) -> tuple[str, str]:
    if not doc:
        return default_title(slug, 'en'), default_body(slug, 'en')
    title_en = (doc.title_en or '').strip()
    body_en = (doc.body_en or '').strip()
    if title_en and body_en:
        return title_en, body_en
    try:
        translator = Translator()
        if not title_en:
            title_en = async_to_sync(translate_text_to)(translator, title_fr, 'en', 'fr')
        if not body_en:
            body_en = translate_long_text_sync(body_fr, 'en')
        doc.title_en = title_en
        doc.body_en = body_en
        doc.save(update_fields=['title_en', 'body_en'])
        return title_en, body_en
    except Exception as exc:  # pragma: no cover - réseau / quota API
        logger.warning('LegalDocument EN autofill failed (%s): %s', slug, exc)
        return default_title(slug, 'en'), default_body(slug, 'en')


def _resolve_other_lang(
    doc: LegalDocument | None,
    slug: str,
    lang: str,
    title_fr: str,
    body_fr: str,
) -> tuple[str, str]:
    if not doc:
        try:
            translator = Translator()
            t = async_to_sync(translate_text_to)(translator, title_fr, googletrans_dest(lang), 'fr')
            b = translate_long_text_sync(body_fr, lang)
            return t, b
        except Exception as exc:
            logger.warning('LegalDocument translate %s (no row) failed: %s', lang, exc)
            return title_fr, body_fr

    cache_raw = doc.translations_cache or {}
    cache: dict[str, Any] = copy.deepcopy(cache_raw) if isinstance(cache_raw, dict) else {}
    entry = cache.get(lang)
    if isinstance(entry, dict):
        te = (entry.get('title') or '').strip()
        be = (entry.get('body') or '').strip()
        if te and be:
            return te, be
    try:
        translator = Translator()
        t = async_to_sync(translate_text_to)(translator, title_fr, googletrans_dest(lang), 'fr')
        b = translate_long_text_sync(body_fr, lang)
        cache[lang] = {'title': t, 'body': b}
        doc.translations_cache = cache
        doc.save(update_fields=['translations_cache'])
        return t, b
    except Exception as exc:
        logger.warning('LegalDocument translate %s failed: %s', lang, exc)
        return title_fr, body_fr


def build_legal_api_response(slug: str, lang_raw: str | None) -> dict[str, Any]:
    requested = normalize_legal_lang(lang_raw)
    content_lang = 'fr' if requested == 'fon' else requested

    doc = LegalDocument.objects.filter(slug=slug).first()
    title_fr, body_fr = _canonical_fr(doc, slug)

    if content_lang == 'fr':
        title, body = title_fr, body_fr
    elif content_lang == 'en':
        title, body = _resolve_en(doc, slug, title_fr, body_fr)
    else:
        title, body = _resolve_other_lang(doc, slug, content_lang, title_fr, body_fr)

    updated_at = doc.updated_at.isoformat() if doc and doc.updated_at else None

    payload: dict[str, Any] = {
        'slug': slug,
        'lang': requested,
        'title': title,
        'body': body,
        'updated_at': updated_at,
    }
    if slug == LegalDocument.SLUG_CONTACT:
        raw_mail = ((doc.contact_email if doc else '') or '').strip()
        payload['contact_email'] = raw_mail or 'support@pinova.app'
    return payload
