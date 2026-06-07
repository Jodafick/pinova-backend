"""Recherche PostgreSQL pg_trgm — remplace le tri fuzzy Python pour 100k+ users."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from django.db.models import FloatField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce, Greatest

from pins.models import Board, Hashtag, Pin

# Seuil minimal de similarité trigram (0–1).
TRGM_MIN_SIMILARITY = 0.08
# Équivalent approximatif de fuzzy_score < 0.22 pour les reco header-search.
TRGM_RECOMMENDED_MIN_SIMILARITY = 0.15


def postgres_trgm_enabled() -> bool:
    return connection.vendor == 'postgresql' and getattr(settings, 'SEARCH_USE_TRIGRAM', True)


def _annotate_pin_similarity(qs: QuerySet, query: str) -> QuerySet:
    q = (query or '').strip()
    if not q:
        return qs.none()

    hashtag_best = (
        Hashtag.objects.filter(pins=OuterRef('pk'))
        .annotate(sim=TrigramSimilarity('name', q))
        .order_by('-sim')
        .values('sim')[:1]
    )

    return qs.annotate(
        _title_sim=TrigramSimilarity('title', q),
        _desc_sim=TrigramSimilarity('description', q),
        _author_sim=TrigramSimilarity('author__username', q),
        _hashtag_sim=Coalesce(Subquery(hashtag_best, output_field=FloatField()), 0.0),
    ).annotate(
        search_similarity=Greatest('_title_sim', '_desc_sim', '_author_sim', '_hashtag_sim'),
    )


def search_pins_postgres(base_qs: QuerySet, query: str, *, limit: int) -> list[Pin]:
    q = (query or '').strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 200))
    qs = (
        _annotate_pin_similarity(base_qs.select_related('author', 'topic'), q)
        .filter(search_similarity__gte=TRGM_MIN_SIMILARITY)
        .order_by('-search_similarity', '-created_at')[:limit]
    )
    return list(qs)


def pin_matches_query_postgres(pin: Pin, query: str, *, min_similarity: float = TRGM_RECOMMENDED_MIN_SIMILARITY) -> bool:
    q = (query or '').strip()
    if not q:
        return True
    scored = (
        _annotate_pin_similarity(Pin.objects.filter(pk=pin.pk), q)
        .filter(search_similarity__gte=min_similarity)
        .exists()
    )
    return scored


def search_users_postgres(
    base_qs: QuerySet,
    query: str,
    *,
    limit: int,
) -> list[User]:
    q = (query or '').strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 100))
    qs = (
        base_qs.select_related('profile')
        .annotate(
            _username_sim=TrigramSimilarity('username', q),
            _display_sim=TrigramSimilarity('profile__display_name', q),
        )
        .annotate(search_similarity=Greatest('_username_sim', '_display_sim'))
        .filter(search_similarity__gte=TRGM_MIN_SIMILARITY)
        .order_by('-search_similarity', 'username')[:limit]
    )
    return list(qs)


def search_boards_postgres(base_qs: QuerySet, query: str, *, limit: int) -> list[Board]:
    q = (query or '').strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 400))
    qs = (
        base_qs.select_related('user')
        .prefetch_related('collaborators')
        .annotate(
            _name_sim=TrigramSimilarity('name', q),
            _desc_sim=TrigramSimilarity('description', q),
            _owner_sim=TrigramSimilarity('user__username', q),
        )
        .annotate(search_similarity=Greatest('_name_sim', '_desc_sim', '_owner_sim'))
        .filter(search_similarity__gte=TRGM_MIN_SIMILARITY)
        .order_by('-search_similarity', '-created_at')[:limit]
    )
    return list(qs.distinct())


def broad_pin_q_fallback(search: str) -> Q:
    """Fallback SQLite / trigram désactivé — filtre icontains par jetons."""
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
