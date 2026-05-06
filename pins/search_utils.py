"""Utilitaires de recherche floue (pins / texte) — compatible SQLite et PostgreSQL."""

from __future__ import annotations

from difflib import SequenceMatcher

from django.db.models import Q


def fuzzy_score(query: str, *texts: str) -> float:
    q = (query or '').strip().lower()
    if not q:
        return 0.0
    best = 0.0
    for raw in texts:
        t = (raw or '').strip().lower()
        if not t:
            continue
        if q in t:
            best = max(best, 0.92 + 0.08 * min(len(q) / max(len(t), 1), 1.0))
        best = max(best, SequenceMatcher(None, q, t).ratio())
    return best


def broad_pin_q(search: str) -> Q:
    """OR sur les jetons : correspondance large puis tri flou côté Python."""
    s = (search or '').strip()
    if not s:
        return Q(pk__in=[])
    tokens = [t for t in s.replace(',', ' ').split() if t]
    if not tokens:
        return Q(pk__in=[])
    combined = Q()
    for tok in tokens:
        combined |= (
            Q(title__icontains=tok)
            | Q(description__icontains=tok)
            | Q(author__username__icontains=tok)
            | Q(hashtags__name__icontains=tok)
            | Q(invisible_tags__tag__icontains=tok)
        )
    return combined
