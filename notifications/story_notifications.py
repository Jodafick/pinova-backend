from __future__ import annotations

from django.contrib.auth.models import User

from notifications.notification_i18n import create_localized_notification
from pins.models import Pin


def notify_followers_new_story(*, author: User, pin: Pin, limit: int = 400) -> None:
    """
    Alerte les abonnés qu'une nouvelle story éphémère est disponible (best-effort, plafonné).
    """
    if not pin.is_story or not author.pk:
        return
    try:
        author_profile = author.profile
    except Exception:
        return
    follower_profiles = list(author_profile.followers.all().order_by('-id')[: max(1, limit)])
    follower_ids = [p.user_id for p in follower_profiles if p.user_id and p.user_id != author.pk]
    if not follower_ids:
        return
    author_name = author.username or 'créateur'
    for follower in User.objects.filter(pk__in=follower_ids, is_active=True).only('id'):
        create_localized_notification(
            recipient=follower,
            sender=author,
            notification_type='system',
            title_fr='Nouvelle story',
            message_fr=f'{author_name} a publié une story.',
            pin_id=pin.id,
            pin_slug=pin.slug,
            metadata={
                'kind': 'story_new_from_following',
                'is_story': True,
                'delivery_mode': 'ws_fallback_push',
            },
        )
