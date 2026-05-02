"""Règles de visibilité des pins (fil principal, stories expirées)."""

from django.utils import timezone

from .models import Pin


def pin_is_visible_for_request(pin: Pin, request) -> bool:
    """Aligné sur PinViewSet.get_queryset pour une instance."""
    user = request.user if request.user.is_authenticated else None
    if getattr(pin, 'moderation_hidden', False):
        if not user or user.id != pin.author_id:
            return False
    now = timezone.now()
    sched_ok = pin.scheduled_publish_at is None or pin.scheduled_publish_at <= now
    if not sched_ok and not (user and user.id == pin.author_id):
        return False
    if pin.is_story and pin.story_expires_at and pin.story_expires_at <= now:
        if not user or user.id != pin.author_id:
            return False
    if not user:
        return (
            pin.visibility == Pin.VISIBILITY_PUBLIC
            and not getattr(pin.author.profile, 'private_profile', False)
        )
    if user.id == pin.author_id:
        return True
    my_profile = user.profile
    if pin.visibility == Pin.VISIBILITY_PUBLIC and not pin.author.profile.private_profile:
        return True
    if pin.visibility == Pin.VISIBILITY_FOLLOWERS and pin.author.profile.followers.filter(pk=my_profile.pk).exists():
        return True
    if pin.author.profile.private_profile and pin.author.profile.followers.filter(pk=my_profile.pk).exists():
        return True
    return False
