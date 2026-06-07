"""Pins à publication différée : notifications auteur puis nettoyage de scheduled_publish_at."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from urllib.parse import quote

from notifications.notification_i18n import create_localized_notification
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
            slug = quote(str(pin.slug), safe='')
            action = f'/?story={slug}' if pin.is_story else f'/pin/{pin.slug}'
            create_localized_notification(
                recipient=pin.author,
                sender=None,
                notification_type='scheduled_publish',
                title_fr='Pin publié',
                message_fr=(
                    f'« {_truncate_title(pin.title)} » est maintenant en ligne après publication planifiée.'
                ),
                action_url=action,
                pin_id=pin.id,
                pin_slug=pin.slug,
                metadata={
                    'event': 'scheduled_publish',
                    'published_at_iso': now_iso,
                    'is_story': pin.is_story,
                    'kind': 'scheduled_publish',
                    'delivery_mode': 'ws_and_push',
                    'in_app_toast': True,
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
