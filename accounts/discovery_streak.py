"""Streak découverte non punitive — pause douce, pas de pénalité feed."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


GRACE_DAYS = 3


def record_discovery_visit(profile) -> dict:
    """
    Incrémente le streak si nouvelle journée de visite Discover.
    Gap > GRACE_DAYS : reprise à 1 (pas de reset agressif à 0 ni impact feed).
    """
    today = timezone.localdate()
    last = profile.discovery_streak_last_date
    count = int(profile.discovery_streak_count or 0)
    best = int(profile.discovery_streak_best or 0)

    if last == today:
        return _payload(profile, paused=False)

    if last is None:
        count = 1
    else:
        gap = (today - last).days
        if gap == 1:
            count += 1
        elif gap <= GRACE_DAYS:
            count += 1
        else:
            count = 1

    best = max(best, count)
    profile.discovery_streak_count = count
    profile.discovery_streak_best = best
    profile.discovery_streak_last_date = today
    profile.save(update_fields=['discovery_streak_count', 'discovery_streak_best', 'discovery_streak_last_date'])

    return _payload(profile, paused=False)


def discovery_streak_payload(profile) -> dict:
    today = timezone.localdate()
    last = profile.discovery_streak_last_date
    paused = False
    if last and last != today:
        gap = (today - last).days
        if gap > GRACE_DAYS:
            paused = True
    return _payload(profile, paused=paused)


def _payload(profile, *, paused: bool) -> dict:
    return {
        'count': int(profile.discovery_streak_count or 0),
        'best': int(profile.discovery_streak_best or 0),
        'last_date': profile.discovery_streak_last_date.isoformat() if profile.discovery_streak_last_date else None,
        'paused': paused,
        'grace_days': GRACE_DAYS,
    }
