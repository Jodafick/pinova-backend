from __future__ import annotations

from django.core.cache import cache

REFERRAL_LB_CACHE_TTL_SEC = 4


def referral_leaderboard_cache_key(*, contest_id: int, limit: int) -> str:
    return f'referral_lb:v1:{contest_id}:{limit}'


def get_cached_json(key: str):
    return cache.get(key)


def set_cached_json(key: str, payload: dict, ttl: int = REFERRAL_LB_CACHE_TTL_SEC) -> None:
    cache.set(key, payload, timeout=ttl)


def invalidate_referral_leaderboard_cache(contest_id: int) -> None:
    for lim in (10, 25, 40, 50, 75, 100, 120, 150, 180, 200):
        cache.delete(referral_leaderboard_cache_key(contest_id=contest_id, limit=lim))
