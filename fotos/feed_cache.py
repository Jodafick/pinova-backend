"""Cache intelligent feed (Redis / LocMem) + métriques hit rate."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger('fotoce.cache')

HOME_FEED_PAGE1_TTL = 60
DISCOVER_PAGE1_TTL = 120
CREATOR_STATS_TTL = 90

DISCOVER_GLOBAL_VER_KEY = 'fotoce:feed:discover:global_ver'


def _topic_token(topic: str) -> str:
    t = (topic or '').strip()
    if not t:
        return 'all'
    return hashlib.sha256(t.encode('utf-8')).hexdigest()[:12]


def _page_size_token(page_size: int) -> str:
    return str(max(1, min(int(page_size), 100)))


def _safe_incr(key: str, *, initial: int = 2) -> int:
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, initial, timeout=None)
        return initial


def skip_feed_cache(request) -> bool:
    return str(getattr(request, 'query_params', {}).get('no_cache') or '').lower() in (
        '1',
        'true',
        'yes',
    )


def _home_feed_version_key(user_id: int) -> str:
    return f'fotoce:feed:home:ver:{user_id}'


def get_home_feed_version(user_id: int) -> int:
    return int(cache.get(_home_feed_version_key(user_id), 1))


def bump_home_feed_version(user_id: int) -> None:
    _safe_incr(_home_feed_version_key(user_id))


def home_feed_page1_key(user_id: int, *, topic: str, page_size: int, reco_on: bool) -> str:
    ver = get_home_feed_version(user_id)
    return (
        f'fotoce:feed:home:v{ver}:{user_id}:p1:'
        f'{_topic_token(topic)}:ps{_page_size_token(page_size)}:reco{int(reco_on)}'
    )


def get_discover_global_version() -> int:
    return int(cache.get(DISCOVER_GLOBAL_VER_KEY, 1))


def bump_discover_global_version() -> None:
    _safe_incr(DISCOVER_GLOBAL_VER_KEY)


def _discover_user_version_key(user_id: int) -> str:
    return f'fotoce:feed:discover:user_ver:{user_id}'


def get_discover_user_version(user_id: int) -> int:
    return int(cache.get(_discover_user_version_key(user_id), 1))


def bump_discover_user_version(user_id: int) -> None:
    _safe_incr(_discover_user_version_key(user_id))


def discover_page1_global_key(*, topic: str, page_size: int) -> str:
    gver = get_discover_global_version()
    return (
        f'fotoce:feed:discover:g{gver}:global:p1:'
        f'{_topic_token(topic)}:ps{_page_size_token(page_size)}'
    )


def discover_page1_user_key(user_id: int, *, topic: str, page_size: int) -> str:
    gver = get_discover_global_version()
    uver = get_discover_user_version(user_id)
    return (
        f'fotoce:feed:discover:g{gver}:u{uver}:{user_id}:p1:'
        f'{_topic_token(topic)}:ps{_page_size_token(page_size)}'
    )


def discover_page1_key(request, *, topic: str, page_size: int) -> str:
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return discover_page1_user_key(user.id, topic=topic, page_size=page_size)
    return discover_page1_global_key(topic=topic, page_size=page_size)


def _creator_stats_version_key(user_id: int) -> str:
    return f'fotoce:creator_stats:ver:{user_id}'


def get_creator_stats_version(user_id: int) -> int:
    return int(cache.get(_creator_stats_version_key(user_id), 1))


def bump_creator_stats_version(user_id: int) -> None:
    _safe_incr(_creator_stats_version_key(user_id))


def creator_stats_cache_key(
    user_id: int,
    *,
    totals_only: bool,
    top_page: int,
    top_page_size: int,
) -> str:
    ver = get_creator_stats_version(user_id)
    return (
        f'fotoce:creator_stats:v{ver}:{user_id}:'
        f'{int(totals_only)}:{top_page}:{top_page_size}'
    )


def invalidate_home_feed_for_author_followers(author) -> None:
    """Invalide page 1 home_feed des abonnés (+ auteur) via bump de version."""
    from accounts.models import Profile

    bump_home_feed_version(author.id)
    follower_user_ids = Profile.objects.filter(following=author.profile).values_list(
        'user_id',
        flat=True,
    )
    for uid in follower_user_ids:
        bump_home_feed_version(uid)


def invalidate_on_public_foto_change(*, author_id: int, invalidate_discover: bool = True) -> None:
    bump_creator_stats_version(author_id)
    if invalidate_discover:
        bump_discover_global_version()


def log_cache_event(
    *,
    cache_scope: str,
    cache_key: str,
    hit: bool,
    user_id: int | None = None,
    ttl: int | None = None,
) -> None:
    payload = {
        'event': 'cache_hit' if hit else 'cache_miss',
        'cache_scope': cache_scope,
        'cache_key': cache_key,
        'user_id': user_id,
        'ttl': ttl,
    }
    logger.info(json.dumps(payload, ensure_ascii=False), extra=payload)


def get_cached_payload(
    key: str,
    *,
    cache_scope: str,
    user_id: int | None = None,
) -> tuple[Any | None, bool]:
    payload = cache.get(key)
    hit = payload is not None
    log_cache_event(cache_scope=cache_scope, cache_key=key, hit=hit, user_id=user_id)
    return payload, hit


def _json_safe_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


def set_cached_payload(
    key: str,
    payload: Any,
    ttl: int,
    *,
    cache_scope: str,
    user_id: int | None = None,
) -> None:
    cache.set(key, _json_safe_payload(payload), timeout=ttl)
    log_cache_event(
        cache_scope=cache_scope,
        cache_key=key,
        hit=False,
        user_id=user_id,
        ttl=ttl,
    )


def apply_cache_header(response, *, hit: bool):
    response['X-Cache'] = 'HIT' if hit else 'MISS'
    return response


def warm_discover_page1_cache(*, topic: str = '', page_size: int = 10) -> str:
    """Pré-chauffe le cache discover page 1 (anon global). Retourne la clé écrite."""
    from django.test import RequestFactory
    from rest_framework.request import Request

    from .views import FotoViewSet

    factory = RequestFactory()
    path = f'/api/fotos/discover/?page=1&page_size={page_size}'
    if topic:
        path += f'&topic={topic}'
    wsgi_request = factory.get(path)
    request = Request(wsgi_request)
    request.user = AnonymousUser()

    viewset = FotoViewSet()
    viewset.action = 'discover'
    viewset.request = request
    viewset.format_kwarg = None
    response = viewset.discover(request)
    if response.status_code != 200:
        raise RuntimeError(f'warm_discover failed: HTTP {response.status_code}')

    key = discover_page1_global_key(topic=topic, page_size=page_size)
    set_cached_payload(
        key,
        response.data,
        DISCOVER_PAGE1_TTL,
        cache_scope='discover_page1_warm',
        user_id=None,
    )
    apply_cache_header(response, hit=False)
    return key
