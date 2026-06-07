"""Façade recherche — Typesense (Phase 2) avec fallback PostgreSQL pg_trgm."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Case, IntegerField, QuerySet, Value, When

from pins.models import Board, Pin
from pins.search_utils import broad_pin_q, fuzzy_score

from . import postgres
from . import typesense_client

logger = logging.getLogger('pinova.search')


class SearchEngineUnavailable(Exception):
    """Moteur Typesense indisponible — le caller doit basculer sur PostgreSQL."""


def _use_typesense() -> bool:
    return (
        getattr(settings, 'SEARCH_ENGINE', 'postgres') == 'typesense'
        and typesense_client.typesense_configured()
    )


def search_pins(
    base_qs: QuerySet,
    query: str,
    *,
    limit: int,
    exclude_author_id: int | None = None,
) -> list[Pin]:
    q = (query or '').strip()
    if not q:
        return []

    if _use_typesense():
        try:
            return _search_pins_typesense(
                base_qs,
                q,
                limit=limit,
                exclude_author_id=exclude_author_id,
            )
        except (typesense_client.TypesenseUnavailable, SearchEngineUnavailable, Exception) as exc:
            logger.warning('Typesense pins search failed, fallback postgres: %s', exc)

    if postgres.postgres_trgm_enabled():
        return postgres.search_pins_postgres(base_qs, q, limit=limit)

    return _search_pins_legacy(base_qs, q, limit=limit)


def _search_pins_typesense(
    base_qs: QuerySet,
    query: str,
    *,
    limit: int,
    exclude_author_id: int | None,
) -> list[Pin]:
    ids = typesense_client.search_pin_ids(query, limit=limit * 3, exclude_author_id=exclude_author_id)
    if not ids:
        return []
    visible_ids = set(base_qs.filter(pk__in=ids).values_list('pk', flat=True))
    ordered = [pk for pk in ids if pk in visible_ids][:limit]
    if not ordered:
        return []
    order = Case(*[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ordered)], output_field=IntegerField())
    return list(base_qs.filter(pk__in=ordered).select_related('author', 'topic').annotate(_sort=order).order_by('_sort'))


def _search_pins_legacy(base_qs: QuerySet, query: str, *, limit: int) -> list[Pin]:
    candidates = list(base_qs.filter(broad_pin_q(query)).select_related('author', 'topic')[:150])
    candidates.sort(
        key=lambda p: -fuzzy_score(
            query,
            p.title or '',
            p.description or '',
            p.author.username,
        )
    )
    return candidates[:limit]


def search_users(base_qs: QuerySet, query: str, *, limit: int) -> list[User]:
    q = (query or '').strip()
    if not q:
        return []

    if _use_typesense():
        try:
            return _search_users_typesense(base_qs, q, limit=limit)
        except (typesense_client.TypesenseUnavailable, SearchEngineUnavailable, Exception) as exc:
            logger.warning('Typesense users search failed, fallback postgres: %s', exc)

    if postgres.postgres_trgm_enabled():
        return postgres.search_users_postgres(base_qs, q, limit=limit)

    return _search_users_legacy(base_qs, q, limit=limit)


def _search_users_typesense(base_qs: QuerySet, query: str, *, limit: int) -> list[User]:
    ids = typesense_client.search_user_ids(query, limit=limit * 3)
    if not ids:
        return []
    visible = {u.pk: u for u in base_qs.filter(pk__in=ids).select_related('profile')}
    return [visible[pk] for pk in ids if pk in visible][:limit]


def _search_users_legacy(base_qs: QuerySet, query: str, *, limit: int) -> list[User]:
    from django.db.models import Q

    users_qs = base_qs.select_related('profile').filter(
        Q(username__icontains=query) | Q(profile__display_name__icontains=query)
    )
    ul = list(users_qs[:80])
    ul.sort(
        key=lambda u: -fuzzy_score(
            query,
            u.username,
            (u.profile.display_name or '') if getattr(u, 'profile', None) else '',
        )
    )
    return ul[:limit]


def search_boards(base_qs: QuerySet, query: str, *, limit: int, viewer_id: int | None = None) -> list[Board]:
    q = (query or '').strip()
    if not q:
        return []

    if _use_typesense():
        try:
            return _search_boards_typesense(base_qs, q, limit=limit, viewer_id=viewer_id)
        except (typesense_client.TypesenseUnavailable, SearchEngineUnavailable, Exception) as exc:
            logger.warning('Typesense boards search failed, fallback postgres: %s', exc)

    if postgres.postgres_trgm_enabled():
        return postgres.search_boards_postgres(base_qs, q, limit=limit)

    return _search_boards_legacy(base_qs, q, limit=limit)


def _search_boards_typesense(
    base_qs: QuerySet,
    query: str,
    *,
    limit: int,
    viewer_id: int | None,
) -> list[Board]:
    ids = typesense_client.search_board_ids(query, limit=limit * 2, viewer_id=viewer_id)
    if not ids:
        return []
    visible_ids = set(base_qs.filter(pk__in=ids).values_list('pk', flat=True))
    ordered = [pk for pk in ids if pk in visible_ids][:limit]
    if not ordered:
        return []
    order = Case(*[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ordered)], output_field=IntegerField())
    return list(
        base_qs.filter(pk__in=ordered)
        .select_related('user')
        .prefetch_related('collaborators')
        .annotate(_sort=order)
        .order_by('_sort')
    )


def _search_boards_legacy(base_qs: QuerySet, query: str, *, limit: int) -> list[Board]:
    from django.db.models import Q

    boards_qs = base_qs.filter(
        Q(name__icontains=query) | Q(description__icontains=query) | Q(user__username__icontains=query)
    ).distinct()
    candidates = list(boards_qs.select_related('user').prefetch_related('collaborators')[:80])
    candidates.sort(
        key=lambda b: -fuzzy_score(
            query,
            b.name or '',
            b.description or '',
            b.user.username if getattr(b, 'user', None) else '',
        )
    )
    return candidates[:limit]


def pin_matches_query(pin: Pin, query: str, *, min_score: float = 0.22) -> bool:
    q = (query or '').strip()
    if not q:
        return True
    if postgres.postgres_trgm_enabled():
        return postgres.pin_matches_query_postgres(
            pin,
            q,
            min_similarity=postgres.TRGM_RECOMMENDED_MIN_SIMILARITY,
        )
    return fuzzy_score(q, pin.title or '', pin.description or '', pin.author.username) >= min_score


def discover_pins_filter(base_qs: QuerySet, query: str) -> QuerySet:
    """Filtre discover?q= avec ranking SQL si pg_trgm disponible."""
    q = (query or '').strip()
    if not q:
        return base_qs
    if _use_typesense():
        try:
            pins = _search_pins_typesense(base_qs, q, limit=200, exclude_author_id=None)
            ids = [p.pk for p in pins]
            if not ids:
                return base_qs.none()
            order = Case(*[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ids)], output_field=IntegerField())
            return base_qs.filter(pk__in=ids).annotate(_discover_sort=order).order_by('_discover_sort')
        except Exception as exc:
            logger.warning('Typesense discover filter failed, fallback postgres: %s', exc)
    if postgres.postgres_trgm_enabled():
        pins = postgres.search_pins_postgres(base_qs, q, limit=200)
        ids = [p.pk for p in pins]
        if not ids:
            return base_qs.none()
        order = Case(*[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ids)], output_field=IntegerField())
        return base_qs.filter(pk__in=ids).annotate(_discover_sort=order).order_by('_discover_sort')
    return base_qs.filter(broad_pin_q(q))
