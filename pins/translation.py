import asyncio
from googletrans import Translator
from langdetect import detect, LangDetectException

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


async def translate_text_to(translator: Translator, text: str, target_lang: str, source_lang: str = SOURCE_LANG) -> str:
    """Variante multi-langue basée sur la même stratégie de retry."""
    if not text or not text.strip():
        return text

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await translator.translate(text, src=source_lang, dest=target_lang)
            return result.text
        except Exception as exc:  # pragma: no cover - erreurs réseau/API
            last_error = exc
            await asyncio.sleep(0.5 * attempt)

    raise RuntimeError(f"Echec de traduction: {text!r}") from last_error


def detect_original_language(text: str) -> str:
    """Détecte la langue source pour métadonnées (sans forcer googletrans)."""
    if not text or not text.strip():
        return 'auto'
    try:
        return detect(text)
    except LangDetectException:
        return 'auto'

