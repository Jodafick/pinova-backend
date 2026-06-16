"""Utilitaires de recherche — fuzzy legacy + filtres icontains (fallback SQLite)."""

from __future__ import annotations

from difflib import SequenceMatcher

from django.db.models import Q

from fotos.search.postgres import broad_foto_q_fallback


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


def broad_foto_q(search: str) -> Q:
    """Fallback icontains — préférer fotos.search.service.search_pins avec pg_trgm."""
    return broad_foto_q_fallback(search)
