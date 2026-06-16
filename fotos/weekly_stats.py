"""Stats vues créateur sur fenêtre glissante (digest & dashboard Pro)."""
from __future__ import annotations

from math import ceil
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from fotoce_backend.media_serving.cache import build_versioned_media_url

from .models import Comment, Like, Foto, FotoViewEvent, Save


def creator_period_engagement_totals(user, since):
    """Likes / saves / commentaires sur les fotos de l’auteur pendant [since, now]."""
    likes = Like.objects.filter(foto__author=user, created_at__gte=since).count()
    saves = Save.objects.filter(foto__author=user, created_at__gte=since).count()
    comments = Comment.objects.filter(foto__author=user, created_at__gte=since).count()
    distinct_viewers = (
        FotoViewEvent.objects.filter(foto__author=user, created_at__gte=since).aggregate(
            n=Count('user_id', distinct=True)
        )['n']
        or 0
    )
    return {
        'likes_period': likes,
        'saves_period': saves,
        'comments_period': comments,
        'distinct_viewers_period': int(distinct_viewers),
    }


def creator_period_engagement_between(user, start, end_exclusive):
    """Même métrique que `creator_period_engagement_totals`, sur [start, end_exclusive)."""
    likes = Like.objects.filter(
        foto__author=user,
        created_at__gte=start,
        created_at__lt=end_exclusive,
    ).count()
    saves = Save.objects.filter(
        foto__author=user,
        created_at__gte=start,
        created_at__lt=end_exclusive,
    ).count()
    comments = Comment.objects.filter(
        foto__author=user,
        created_at__gte=start,
        created_at__lt=end_exclusive,
    ).count()
    distinct_viewers = (
        FotoViewEvent.objects.filter(
            foto__author=user,
            created_at__gte=start,
            created_at__lt=end_exclusive,
        ).aggregate(n=Count('user_id', distinct=True))['n']
        or 0
    )
    return {
        'likes_period': likes,
        'saves_period': saves,
        'comments_period': comments,
        'distinct_viewers_period': int(distinct_viewers),
    }


def count_foto_view_events_between(user, start, end_exclusive):
    return FotoViewEvent.objects.filter(
        foto__author=user,
        created_at__gte=start,
        created_at__lt=end_exclusive,
    ).count()


def _foto_counts_in_period(model, foto_ids, user, since):
    if not foto_ids:
        return {}
    return dict(
        model.objects.filter(foto_id__in=foto_ids, foto__author=user, created_at__gte=since)
        .values('foto_id')
        .annotate(c=Count('id'))
        .values_list('foto_id', 'c')
    )


def weekly_creator_pins_page(user, days: int = 7, *, page: int = 1, page_size: int = 20):
    """
    Pins de l'utilisateur classés par nombre de FotoViewEvent sur la fenêtre [days].

    Retourne :
      rows — liste de {'pin': Foto, 'views_week': int} (ordre décroissant des vues)
      total_pins — nombre de fotos ayant au moins une vue sur la période
      total_view_events — nombre total d'événements sur la période
      page, page_size, total_pages
    """
    since = timezone.now() - timedelta(days=days)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 50))

    ranked = (
        FotoViewEvent.objects.filter(foto__author=user, created_at__gte=since)
        .values('foto_id')
        .annotate(views_week=Count('id'))
        .order_by('-views_week', 'foto_id')
    )
    total_events = FotoViewEvent.objects.filter(
        foto__author=user,
        created_at__gte=since,
    ).count()
    total_pins = ranked.count()
    total_pages = max(1, ceil(total_pins / page_size)) if total_pins else 1
    offset = (page - 1) * page_size
    slice_rows = list(ranked[offset : offset + page_size])

    if not slice_rows:
        return [], total_pins, total_events, page, page_size, total_pages

    foto_ids = [r['foto_id'] for r in slice_rows]
    views_map = {r['foto_id']: int(r['views_week']) for r in slice_rows}
    pins_by_id = {p.id: p for p in Foto.objects.filter(id__in=foto_ids).select_related('author')}
    likes_map = _foto_counts_in_period(Like, foto_ids, user, since)
    saves_map = _foto_counts_in_period(Save, foto_ids, user, since)
    comments_map = _foto_counts_in_period(Comment, foto_ids, user, since)

    rows = []
    for r in slice_rows:
        pid = r['foto_id']
        foto = pins_by_id.get(pid)
        if foto is None:
            continue
        rows.append(
            {
                'pin': foto,
                'views_week': views_map[pid],
                'likes_week': int(likes_map.get(pid, 0)),
                'saves_week': int(saves_map.get(pid, 0)),
                'comments_week': int(comments_map.get(pid, 0)),
            }
        )

    return rows, total_pins, total_events, page, page_size, total_pages


def pro_weekly_views_stats(user, days: int = 7):
    """
    Compat digest e-mail : top fotos (ordre vues semaine) avec attribut dynamique views_week.

    Retourne (liste_de_Pin_avec_views_week, total_view_events).
    """
    rows, _total_pins, total_events, _, _, _ = weekly_creator_pins_page(
        user, days=days, page=1, page_size=50
    )
    pins_out = []
    for row in rows:
        foto = row['pin']
        setattr(pin, 'views_week', row['views_week'])
        pins_out.append(foto)
    return pins_out, total_events


def pin_thumbnail_absolute_url(pin, request):
    img = getattr(pin, 'image', None)
    if not img or not getattr(img, 'name', ''):
        return None
    return build_versioned_media_url(request, img)
