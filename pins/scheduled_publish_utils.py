"""Pins à publication différée : notifications auteur puis nettoyage de scheduled_publish_at."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from pins.models import Pin


def _truncate_title(title: str, max_len: int = 140) -> str:
    title = (title or '').strip()
    return title if len(title) <= max_len else title[: max_len - 1] + '…'


def publish_due_scheduled_pins(queryset, *, limit: int = 1000) -> int:
    """
    Pour chaque pin dû dans ce queryset : notification à l'auteur (post_save push),
    puis scheduled_publish_at = None.

    select_for_update n'est pas utilisé (SQLite / compatibilité).

    Retourne le nombre de pins traités.
    """
    limit = max(1, limit)
    with transaction.atomic():
        qs = (
            queryset.filter(scheduled_publish_at__isnull=False, scheduled_publish_at__lte=timezone.now())
            .select_related('author')
            .order_by('scheduled_publish_at', 'pk')[:limit]
        )
        pins = list(qs)
        if not pins:
            return 0

        now_iso = timezone.now().isoformat()
        for pin in pins:
            Notification.objects.create(
                recipient=pin.author,
                sender=None,
                notification_type='scheduled_publish',
                title='Pin publié',
                message=(
                    f'« {_truncate_title(pin.title)} » est maintenant en ligne après publication planifiée.'
                ),
                action_url='/pin/' + pin.slug,
                pin_id=pin.id,
                pin_slug=pin.slug,
                metadata={
                    'event': 'scheduled_publish',
                    'published_at_iso': now_iso,
                },
            )

        cleared_ids = [p.pk for p in pins]
        Pin.objects.filter(pk__in=cleared_ids).update(scheduled_publish_at=None)

    return len(pins)


def publish_user_due_scheduled_pins(user, *, limit: int = 50) -> int:
    """Pins planifiés dus pour un auteur ; appeler depuis GET /api/me/."""
    if not getattr(user, 'pk', None) or not getattr(user, 'is_authenticated', False):
        return 0
    return publish_due_scheduled_pins(Pin.objects.filter(author=user), limit=limit)
