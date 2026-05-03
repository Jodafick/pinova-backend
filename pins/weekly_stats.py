"""Stats vues créateur sur fenêtre glissante (digest & dashboard Pro)."""
from __future__ import annotations

from math import ceil
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import Pin, PinViewEvent


def weekly_creator_pins_page(user, days: int = 7, *, page: int = 1, page_size: int = 20):
    """
    Pins de l'utilisateur classés par nombre de PinViewEvent sur la fenêtre [days].

    Retourne :
      rows — liste de {'pin': Pin, 'views_week': int} (ordre décroissant des vues)
      total_pins — nombre de pins ayant au moins une vue sur la période
      total_view_events — nombre total d'événements sur la période
      page, page_size, total_pages
    """
    since = timezone.now() - timedelta(days=days)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 50))

    ranked = (
        PinViewEvent.objects.filter(pin__author=user, created_at__gte=since)
        .values('pin_id')
        .annotate(views_week=Count('id'))
        .order_by('-views_week', 'pin_id')
    )
    total_events = PinViewEvent.objects.filter(
        pin__author=user,
        created_at__gte=since,
    ).count()
    total_pins = ranked.count()
    total_pages = max(1, ceil(total_pins / page_size)) if total_pins else 1
    offset = (page - 1) * page_size
    slice_rows = list(ranked[offset : offset + page_size])

    if not slice_rows:
        return [], total_pins, total_events, page, page_size, total_pages

    pin_ids = [r['pin_id'] for r in slice_rows]
    views_map = {r['pin_id']: int(r['views_week']) for r in slice_rows}
    pins_by_id = {p.id: p for p in Pin.objects.filter(id__in=pin_ids).select_related('author')}

    rows = []
    for r in slice_rows:
        pid = r['pin_id']
        pin = pins_by_id.get(pid)
        if pin is None:
            continue
        rows.append({'pin': pin, 'views_week': views_map[pid]})

    return rows, total_pins, total_events, page, page_size, total_pages


def pro_weekly_views_stats(user, days: int = 7):
    """
    Compat digest e-mail : top pins (ordre vues semaine) avec attribut dynamique views_week.

    Retourne (liste_de_Pin_avec_views_week, total_view_events).
    """
    rows, _total_pins, total_events, _, _, _ = weekly_creator_pins_page(
        user, days=days, page=1, page_size=50
    )
    pins_out = []
    for row in rows:
        pin = row['pin']
        setattr(pin, 'views_week', row['views_week'])
        pins_out.append(pin)
    return pins_out, total_events


def pin_thumbnail_absolute_url(pin, request):
    img = getattr(pin, 'image', None)
    if not img or not getattr(img, 'name', ''):
        return None
    return request.build_absolute_uri(img.url)
