"""Requêtes agrégées créateur (stats « all time ») — pagination sans grosses jointures ORM."""
from __future__ import annotations

from math import ceil

from django.db.models import Count

from .models import Comment, Like, Foto, FotoViewEvent, Save


def creator_totals_for_user(user):
    """Compteurs globaux pour les fotos de l'utilisateur (requêtes indexées foto_id / author)."""
    my_fotos = Foto.objects.filter(author=user)
    return {
        'fotos': my_fotos.count(),
        'likes': Like.objects.filter(pin__author=user).count(),
        'saves': Save.objects.filter(pin__author=user).count(),
        'comments': Comment.objects.filter(pin__author=user).count(),
        'views': FotoViewEvent.objects.filter(pin__author=user).count(),
    }


def paginated_creator_top_pins(user, *, page: int, page_size: int, pool: int = 400):
    """
    Classement par vues (all time), puis saves / likes / date.

    Seuls les fotos présents dans les `pool` foto_id les plus vus sont classés
    (borne pour rester rapide si l'auteur a des milliers de fotos).

    Retourne (liste_payload, total_classés, page, page_size, total_pages).
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 50))
    pool = max(50, min(int(pool), 2000))

    by_views = (
        FotoViewEvent.objects.filter(pin__author=user)
        .values('foto_id')
        .annotate(views_total=Count('id'))
        .order_by('-views_total', 'foto_id')[:pool]
    )
    view_rows = list(by_views)
    foto_ids = [r['foto_id'] for r in view_rows]
    pins_by_id = {p.id: p for p in Foto.objects.filter(id__in=foto_ids)} if foto_ids else {}
    like_by_pin = dict(
        Like.objects.filter(foto_id__in=foto_ids)
        .values('foto_id')
        .annotate(c=Count('id'))
        .values_list('foto_id', 'c')
    ) if foto_ids else {}
    save_by_pin = dict(
        Save.objects.filter(foto_id__in=foto_ids)
        .values('foto_id')
        .annotate(c=Count('id'))
        .values_list('foto_id', 'c')
    ) if foto_ids else {}

    candidates = []
    for row in view_rows:
        pid = row['foto_id']
        foto = pins_by_id.get(pid)
        if foto is None:
            continue
        candidates.append(
            {
                'pin': foto,
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
