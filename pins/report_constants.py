"""Catégories de signalement (API + admin) — garder aligné avec le frontend."""

from __future__ import annotations

REPORT_CATEGORY_CHOICES = (
    ('harmful', 'Contenu préjudiciable'),
    ('spam_scam', 'Spam, arnaque ou usurpation'),
    ('other', 'Autre'),
)

REPORT_CATEGORY_CODES = frozenset(c for c, _ in REPORT_CATEGORY_CHOICES)
REPORT_DETAILS_MAX_LEN = 2000

# Anciennes catégories (10 motifs) → taxonomie simplifiée 3 branches.
_LEGACY_CATEGORY_MAP: dict[str, str] = {
    'harassment': 'harmful',
    'hate': 'harmful',
    'sexual': 'harmful',
    'violence': 'harmful',
    'illegal': 'harmful',
    'minor': 'harmful',
    'spam': 'spam_scam',
    'impersonation': 'spam_scam',
    'copyright': 'spam_scam',
    'other': 'other',
}


def normalize_report_category(raw: str | None) -> str:
    code = (raw or '').strip().lower()
    if code in REPORT_CATEGORY_CODES:
        return code
    if code in _LEGACY_CATEGORY_MAP:
        return _LEGACY_CATEGORY_MAP[code]
    return 'other'
