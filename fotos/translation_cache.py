"""Cache BD des traductions automatiques googletrans — éviter les doublons inter-requêtes."""

from __future__ import annotations

import hashlib
import logging

from django.db import IntegrityError
from django.db.models import F

from .models import MachineTranslationCache

logger = logging.getLogger(__name__)


def normalize_translation_dest(lang: str | None) -> str:
    """Aligné sur googletrans destinataire (ex. ``zh`` → ``zh-cn``)."""
    c = (lang or '').strip().lower().split('-')[0]
    if not c:
        return 'fr'
    if c == 'zh':
        return 'zh-cn'
    return c.strip().lower()


def normalize_source_iso(lang: str | None) -> str:
    return (lang or 'auto').strip().lower().split('-')[0]


def mt_normalized_text(text: str) -> str:
    return (text or '').strip()


def mt_sha256(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()


def mt_cache_lookup(source_iso: str, target_lang: str, normalized_text: str) -> str | None:
    if not normalized_text:
        return None
    src = normalize_source_iso(source_iso)
    tgt = normalize_translation_dest(target_lang)
    if src == 'auto' or not tgt:
        return None

    digest = mt_sha256(normalized_text)

    qs = MachineTranslationCache.objects.filter(
        source_lang=src,
        target_lang=tgt,
        text_sha256=digest,
    ).values_list('source_text', 'translated_text', 'pk')

    hit = qs.first()
    if not hit:
        return None
    stored_src, translated, pk = hit[0], hit[1], hit[2]
    if stored_src != normalized_text:
        logger.warning('mt_cache_lookup: collision hash ignorée pk=%s', pk)
        return None

    try:
        MachineTranslationCache.objects.filter(pk=pk).update(hits=F('hits') + 1)
    except Exception as exc:
        logger.debug('mt_cache_lookup hits+: %s', exc)

    return translated


def mt_cache_save(source_iso: str, target_lang: str, normalized_text: str, translated: str) -> None:
    if not normalized_text or not (translated or '').strip():
        return
    src = normalize_source_iso(source_iso)
    tgt = normalize_translation_dest(target_lang)
    if src == 'auto':
        return
    out = (translated or '').strip()
    digest = mt_sha256(normalized_text)
    try:
        MachineTranslationCache.objects.create(
            source_lang=src,
            target_lang=tgt,
            text_sha256=digest,
            source_text=normalized_text,
            translated_text=out,
            hits=0,
        )
    except IntegrityError:
        MachineTranslationCache.objects.filter(
            source_lang=src,
            target_lang=tgt,
            text_sha256=digest,
        ).update(translated_text=out)
