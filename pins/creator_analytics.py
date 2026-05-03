"""Requêtes agrégées créateur (stats « all time ») — pagination sans grosses jointures ORM."""
from __future__ import annotations

from math import ceil

from django.db.models import Count

from .models import Comment, Like, Pin, PinViewEvent, Save


def creator_totals_for_user(user):
    """Compteurs globaux pour les pins de l'utilisateur (requêtes indexées pin_id / author)."""
    my_pins = Pin.objects.filter(author=user)
    return {
        'pins': my_pins.count(),
        'likes': Like.objects.filter(pin__author=user).count(),
        'saves': Save.objects.filter(pin__author=user).count(),
        'comments': Comment.objects.filter(pin__author=user).count(),
        'views': PinViewEvent.objects.filter(pin__author=user).count(),
    }


def paginated_creator_top_pins(user, *, page: int, page_size: int, pool: int = 400):
    """
    Classement par vues (all time), puis saves / likes / date.

    Seuls les pins présents dans les `pool` pin_id les plus vus sont classés
    (borne pour rester rapide si l'auteur a des milliers de pins).

    Retourne (liste_payload, total_classés, page, page_size, total_pages).
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 50))
    pool = max(50, min(int(pool), 2000))

    by_views = (
        PinViewEvent.objects.filter(pin__author=user)
        .values('pin_id')
        .annotate(views_total=Count('id'))
        .order_by('-views_total', 'pin_id')[:pool]
    )
    view_rows = list(by_views)
    pin_ids = [r['pin_id'] for r in view_rows]
    pins_by_id = {p.id: p for p in Pin.objects.filter(id__in=pin_ids)} if pin_ids else {}
    like_by_pin = dict(
        Like.objects.filter(pin_id__in=pin_ids)
        .values('pin_id')
        .annotate(c=Count('id'))
        .values_list('pin_id', 'c')
    ) if pin_ids else {}
    save_by_pin = dict(
        Save.objects.filter(pin_id__in=pin_ids)
        .values('pin_id')
        .annotate(c=Count('id'))
        .values_list('pin_id', 'c')
    ) if pin_ids else {}

    candidates = []
    for row in view_rows:
        pid = row['pin_id']
        pin = pins_by_id.get(pid)
        if pin is None:
            continue
        candidates.append(
            {
                'pin': pin,
                'views': row['views_total'],
                'likes': like_by_pin.get(pid, 0),
                'saves': save_by_pin.get(pid, 0),
            }
        )
    candidates.sort(
        key=lambda x: (-x['views'], -x['saves'], -x['likes'], -x['pin'].created_at.timestamp())
    )

    total = len(candidates)
    total_pages = max(1, ceil(total / page_size)) if total else 1
    offset = (page - 1) * page_size
    slice_c = candidates[offset : offset + page_size]
    payload = [
        {
            'id': item['pin'].id,
            'slug': item['pin'].slug,
            'title': item['pin'].title,
            'likes': item['likes'],
            'saves': item['saves'],
            'views': item['views'],
        }
        for item in slice_c
    ]
    return payload, total, page, page_size, total_pages
