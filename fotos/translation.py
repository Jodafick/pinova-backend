import asyncio

from googletrans import Translator
from langdetect import detect, LangDetectException
from asgiref.sync import sync_to_async

from .translation_cache import (
    mt_cache_lookup,
    mt_cache_save,
    mt_normalized_text,
    normalize_source_iso,
    normalize_translation_dest,
)

_mt_cache_lookup_async = sync_to_async(mt_cache_lookup, thread_sensitive=True)
_mt_cache_save_async = sync_to_async(mt_cache_save, thread_sensitive=True)

MAX_RETRIES = 3
SOURCE_LANG = 'auto'
TARGET_LANG = 'fr'


async def translate_text(translator: Translator, text: str) -> str:
    """Traduit un texte simple avec retries."""
    if not text or not text.strip():
        return text

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await translator.translate(text, src=SOURCE_LANG, dest=TARGET_LANG)
            return result.text
        except Exception as exc:  # pragma: no cover - erreurs réseau/API
            last_error = exc
            await asyncio.sleep(0.5 * attempt)

    raise RuntimeError(f"Echec de traduction: {text!r}") from last_error


async def translate_text_to(
    translator: Translator,
    text: str,
    target_lang: str,
    source_lang: str = SOURCE_LANG,
    *,
    use_server_cache: bool = True,
) -> str:
    """Multi-langues + retries ; persistance BD des résultats googletrans (voir ``MachineTranslationCache``).

    Cache uniquement lorsque la langue source n’est pas ``auto`` (explicite ou inférée par détection locale).
    Désactivation : ``use_server_cache=False`` (flux alternatifs, tests)."""

    norm = mt_normalized_text(text)
    if not norm:
        return text

    tgt_google = normalize_translation_dest(target_lang)
    src_requested = normalize_source_iso(source_lang)

    if src_requested == 'auto':
        eff_src_iso = normalize_source_iso(detect_original_language(norm))
    else:
        eff_src_iso = src_requested

    # Pas de deuxième langue identifiable → comportement précédent, sans entrée cache.
    if eff_src_iso != 'auto' and normalize_translation_dest(eff_src_iso) == tgt_google:
        return norm

    can_cache = use_server_cache and eff_src_iso != 'auto'

    if can_cache:
        hit = await _mt_cache_lookup_async(eff_src_iso, target_lang, norm)
        if hit is not None:
            return hit

    google_src = SOURCE_LANG if src_requested == 'auto' else src_requested

    last_error = None
    translated_out = ''
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await translator.translate(norm, src=google_src, dest=tgt_google)
            translated_out = result.text or ''
            break
        except Exception as exc:  # pragma: no cover - erreurs réseau/API
            last_error = exc
            await asyncio.sleep(0.5 * attempt)
    else:
        raise RuntimeError(f"Echec de traduction: {norm!r}") from last_error

    if can_cache and translated_out.strip():
        await _mt_cache_save_async(eff_src_iso, target_lang, norm, translated_out)

    return translated_out


def detect_original_language(text: str) -> str:
    """Détecte la langue source pour métadonnées (sans forcer googletrans)."""
    if not text or not text.strip():
        return 'auto'
    try:
        return detect(text)
    except LangDetectException:
        return 'auto'
