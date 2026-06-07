"""Liste ciblée : insultes violentes / propos haineux / porno explicite (pas vocabulaire sexuel courant)."""

from __future__ import annotations

import re
import unicodedata

from django.conf import settings

# Mots entiers — slurs, insultes graves, marques/sites porno explicites.
_DEFAULT_BLOCKED_WORDS: frozenset[str] = frozenset({
    # Slurs / haine (EN)
    'nigger', 'nigga', 'faggot', 'fagot', 'retard', 'kike', 'chink', 'spic',
    # Slurs / haine (FR)
    'bougnoule', 'youpin', 'bicot', 'raton', 'negro',
    # Insultes violentes (FR)
    'encule', 'enculé', 'enfoire', 'enfoiré', 'ntm',
    # Insultes violentes (EN)
    'motherfucker', 'cunt',
    # Porno explicite — sites / termes sans ambiguïté
    'pornhub', 'xvideos', 'xhamster', 'redtube', 'youporn', 'brazzers',
    'gangbang', 'bukkake', 'deepthroat', 'creampie', 'blowjob', 'handjob',
    'sextape', 'onlyfans',
})

# Expressions multi-mots (espaces normalisés, sans accents).
_DEFAULT_BLOCKED_PHRASES: tuple[str, ...] = (
    # Insultes / menaces (FR)
    'nique ta mere',
    'nique ta mère',
    'va te faire foutre',
    'va te faire enculer',
    'fils de pute',
    'fille de pute',
    'ta gueule',
    'ferme ta gueule',
    'je vais te tuer',
    'je te tue',
    'creve espèce',
    'creve espece',
    # Insultes (EN)
    'fuck you',
    'go kill yourself',
    'kill yourself',
    # Porno explicite (FR / EN)
    'film porno',
    'video porno',
    'vidéo porno',
    'site porno',
    'porno gratuit',
    'free porn',
    'hardcore porn',
    'xxx video',
)

_LEET_MAP = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's',
})


def _configured_words() -> frozenset[str]:
    extra = getattr(settings, 'MODERATION_BLOCKED_WORDS', None) or ()
    return _DEFAULT_BLOCKED_WORDS | frozenset(w.lower().strip() for w in extra if w and w.strip())


def _configured_phrases() -> tuple[str, ...]:
    extra = getattr(settings, 'MODERATION_BLOCKED_PHRASES', None) or ()
    cleaned = tuple(p.lower().strip() for p in extra if p and p.strip())
    return _DEFAULT_BLOCKED_PHRASES + cleaned


def normalize_for_text_scan(text: str) -> str:
    """Minuscules, sans accents, leetspeak basique, espaces unifiés."""
    if not text:
        return ''
    lowered = text.lower().translate(_LEET_MAP)
    decomposed = unicodedata.normalize('NFD', lowered)
    without_accents = ''.join(ch for ch in decomposed if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', without_accents).strip()


def contains_blocked_text(text: str) -> bool:
    """True si le texte contient une insulte violente ou du porno explicite."""
    normalized = normalize_for_text_scan(text)
    if not normalized:
        return False

    for phrase in _configured_phrases():
        phrase_norm = normalize_for_text_scan(phrase)
        if phrase_norm and phrase_norm in normalized:
            return True

    for word in _configured_words():
        word_norm = normalize_for_text_scan(word)
        if not word_norm:
            continue
        if re.search(rf'(?<!\w){re.escape(word_norm)}(?!\w)', normalized, flags=re.UNICODE):
            return True

    return False
