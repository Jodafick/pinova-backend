"""Moteur de recherche Pinova — PostgreSQL pg_trgm (Phase 1) + Typesense (Phase 2)."""

from .service import (
    SearchEngineUnavailable,
    pin_matches_query,
    search_boards,
    search_pins,
    search_users,
)

__all__ = [
    'SearchEngineUnavailable',
    'pin_matches_query',
    'search_boards',
    'search_pins',
    'search_users',
]
