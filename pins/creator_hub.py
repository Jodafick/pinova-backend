"""Hub créateur Pro : pins récents et file de modération commentaires."""
from __future__ import annotations

from math import ceil

from .models import Comment, Pin
from .weekly_stats import pin_thumbnail_absolute_url


def _comment_author_display(comment: Comment) -> str:
    u = comment.user
    profile = getattr(u, 'profile', None)
    if profile and getattr(profile, 'display_name', None) and str(profile.display_name).strip():
        return str(profile.display_name).strip()
    return u.username


def paginated_recent_pins(request, user, page: int, page_size: int):
    """
    Pins de l’auteur du plus récent au plus ancien.
    Retourne (rows, total_items, page, page_size, total_pages).
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 30))
    qs = Pin.objects.filter(author=user).order_by('-created_at')
    total = qs.count()
    total_pages = max(1, ceil(total / page_size)) if total else 1
    offset = (page - 1) * page_size
    pins = qs[offset : offset + page_size]
    rows = []
    for p in pins:
        rows.append(
            {
                'id': p.id,
                'slug': p.slug,
                'title': p.title,
                'thumbnail_url': pin_thumbnail_absolute_url(p, request),
                'visibility': p.visibility,
                'comments_policy': p.comments_policy,
                'created_at': p.created_at.isoformat(),
            }
        )
    return rows, total, page, page_size, total_pages


def paginated_comment_inbox(user, limit: int, offset: int):
    """
    Derniers commentaires sur les pins de l’utilisateur (file modération).
    Retourne (rows, total_count, offset, limit).
    """
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    base = Comment.objects.filter(pin__author=user).select_related('pin', 'user', 'user__profile')
    total = base.count()
    comments = list(base.order_by('-created_at')[offset : offset + limit])
    rows = []
    for c in comments:
        text = (c.text or '').replace('\r\n', '\n').strip()
        rows.append(
            {
                'id': c.id,
                'pin_slug': c.pin.slug,
                'pin_title': c.pin.title,
                'author_username': c.user.username,
                'author_display_name': _comment_author_display(c),
                'text_preview': text[:400],
                'hidden_by_owner': c.hidden_by_owner,
                'moderation_hidden': c.moderation_hidden,
                'created_at': c.created_at.isoformat(),
            }
        )
    return rows, total, offset, limit
