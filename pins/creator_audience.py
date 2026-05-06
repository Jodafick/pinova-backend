"""Agrégations « qui a interagi » sur les pins d’un créateur (Pro) sur une période glissante."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone

from .models import Comment, Like, PinViewEvent, Save

ACTION_LIKES = 'likes'
ACTION_SAVES = 'saves'
ACTION_COMMENTS = 'comments'
ACTION_VIEWS = 'views'

VALID_ACTIONS = frozenset({ACTION_LIKES, ACTION_SAVES, ACTION_COMMENTS, ACTION_VIEWS})


def _avatar_absolute(request, user: User) -> str:
    profile = getattr(user, 'profile', None)
    if not profile:
        return ''
    av = getattr(profile, 'avatar', None)
    if not av or not getattr(av, 'name', ''):
        return ''
    try:
        return request.build_absolute_uri(av.url)
    except Exception:
        return ''


def _actor_row(request, user: User, count: int) -> dict:
    profile = getattr(user, 'profile', None)
    display = (profile.display_name.strip() if profile and profile.display_name else '') or user.username
    color = (profile.avatar_color if profile else '') or '#a3a3a3'
    return {
        'username': user.username,
        'display_name': display,
        'avatar_url': _avatar_absolute(request, user),
        'avatar_color': color,
        'count': int(count),
    }


def creator_engagement_breakdown(request, user, *, action: str, days: int, limit: int) -> dict:
    """
    Retourne total d’actions sur la période, nombre d’acteurs distincts (hors auto-interactions évidentes),
    et les N acteurs les plus actifs.
    """
    assert action in VALID_ACTIONS
    days = max(1, min(int(days), 366))
    limit = max(1, min(int(limit), 80))
    since = timezone.now() - timedelta(days=days)

    def annotate_top(qs, user_field: str):
        return (
            qs.values(f'{user_field}_id')
            .annotate(count=Count('id'))
            .order_by('-count', f'{user_field}_id')[:limit]
        )

    if action == ACTION_LIKES:
        base = Like.objects.filter(pin__author=user, created_at__gte=since).exclude(user=user)
        total = base.count()
        distinct = base.values('user_id').distinct().count()
        rows = list(annotate_top(base, 'user'))
        uid_key = 'user_id'
    elif action == ACTION_SAVES:
        base = Save.objects.filter(pin__author=user, created_at__gte=since).exclude(user=user)
        total = base.count()
        distinct = base.values('user_id').distinct().count()
        rows = list(annotate_top(base, 'user'))
        uid_key = 'user_id'
    elif action == ACTION_COMMENTS:
        base = Comment.objects.filter(pin__author=user, created_at__gte=since).exclude(user=user)
        total = base.count()
        distinct = base.values('user_id').distinct().count()
        rows = list(annotate_top(base, 'user'))
        uid_key = 'user_id'
    else:  # views
        base = PinViewEvent.objects.filter(pin__author=user, created_at__gte=since).exclude(user=user)
        total = base.count()
        distinct = base.values('user_id').distinct().count()
        rows = list(annotate_top(base, 'user'))
        uid_key = 'user_id'

    uids = [r[uid_key] for r in rows if r.get(uid_key)]
    users_by_id = {
        u.id: u
        for u in User.objects.select_related('profile').filter(id__in=uids)
    }
    top_actors = []
    for r in rows:
        uid = r.get(uid_key)
        if not uid:
            continue
        u = users_by_id.get(uid)
        if u is None:
            continue
        top_actors.append(_actor_row(request, u, r['count']))

    return {
        'action': action,
        'period_days': days,
        'since': since.isoformat(),
        'total_actions': total,
        'distinct_actors': distinct,
        'top_actors': top_actors,
    }
