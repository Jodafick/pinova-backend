"""Stats vues créateur sur fenêtre glissante (pour digest & dashboard Pro)."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Pin, PinViewEvent


def pro_weekly_views_stats(user, days: int = 7):
    """
    Retourne (queryset_pins_ordonné, nombre_total_événements_vue).
    Compte uniquement les PinViewEvent (utilisateurs authentifiés ayant envoyé POST /view).
    """
    since = timezone.now() - timedelta(days=days)
    my_pins = Pin.objects.filter(author=user).select_related('author')
    annotated = (
        my_pins.annotate(
            views_week=Count(
                'view_events',
                filter=Q(view_events__created_at__gte=since),
            ),
        )
        .filter(views_week__gt=0)
        .order_by('-views_week', '-created_at')
    )
    total_events = PinViewEvent.objects.filter(
        pin__author=user,
        created_at__gte=since,
    ).count()
    return annotated, int(total_events)


def pin_thumbnail_absolute_url(pin, request):
    img = getattr(pin, 'image', None)
    if not img or not getattr(img, 'name', ''):
        return None
    return request.build_absolute_uri(img.url)
