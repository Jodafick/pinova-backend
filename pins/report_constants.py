"""Catégories de signalement (API + admin) — garder aligné avec le frontend."""

from __future__ import annotations

REPORT_CATEGORY_CHOICES = (
    ('spam', 'Spam ou publicité'),
    ('harassment', 'Harcèlement ou intimidation'),
    ('hate', 'Haine ou discrimination'),
    ('sexual', 'Contenu sexuel ou nudité non autorisée'),
    ('violence', 'Violence ou danger'),
    ('illegal', 'Activité illégale'),
    ('minor', 'Sécurité des mineurs'),
    ('impersonation', 'Usurpation ou arnaque'),
    ('copyright', 'Propriété intellectuelle'),
    ('other', 'Autre'),
)

REPORT_CATEGORY_CODES = frozenset(c for c, _ in REPORT_CATEGORY_CHOICES)
REPORT_DETAILS_MAX_LEN = 2000


def normalize_report_category(raw: str | None) -> str:
    code = (raw or '').strip().lower()
    if code in REPORT_CATEGORY_CODES:
        return code
    return 'other'
