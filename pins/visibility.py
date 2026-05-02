"""Règles de visibilité des pins (fil principal, stories expirées, contenu sensible)."""

from datetime import date

from django.db.models import Q
from django.utils import timezone

from .models import Pin


def profile_is_verified_adult(profile) -> bool:
    """≥18 ans avec date de naissance renseignée."""
    if profile is None:
        return False
    bd = getattr(profile, 'birth_date', None)
    if bd is None:
        return False
    today = date.today()
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    return age >= 18


def viewer_is_verified_adult(request) -> bool:
    if not request.user.is_authenticated:
        return False
    return profile_is_verified_adult(getattr(request.user, 'profile', None))


def sensitive_pin_allowed_for_viewer(pin: Pin, request) -> bool:
    """Pins `media_sensitive_blur` : réservés aux adultes vérifiés ; l’auteur voit toujours le sien."""
    if not getattr(pin, 'media_sensitive_blur', False):
        return True
    user = request.user if request.user.is_authenticated else None
    if user and user.id == pin.author_id:
        return True
    return viewer_is_verified_adult(request)


def sensitive_pins_query_filter(request):
    """Filtre queryset : masque les pins sensibles pour mineurs / anonymes (sauf auteur)."""
    if viewer_is_verified_adult(request):
        return Q()
    user = request.user if request.user.is_authenticated else None
    if user:
        return Q(media_sensitive_blur=False) | Q(author=user)
    return Q(media_sensitive_blur=False)


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
        ok = (
            pin.visibility == Pin.VISIBILITY_PUBLIC
            and not getattr(pin.author.profile, 'private_profile', False)
        )
        return ok and sensitive_pin_allowed_for_viewer(pin, request)
    if user.id == pin.author_id:
        return True
    my_profile = user.profile
    if pin.visibility == Pin.VISIBILITY_PUBLIC and not pin.author.profile.private_profile:
        return sensitive_pin_allowed_for_viewer(pin, request)
    if pin.visibility == Pin.VISIBILITY_FOLLOWERS and pin.author.profile.followers.filter(pk=my_profile.pk).exists():
        return sensitive_pin_allowed_for_viewer(pin, request)
    if pin.author.profile.private_profile and pin.author.profile.followers.filter(pk=my_profile.pk).exists():
        return sensitive_pin_allowed_for_viewer(pin, request)
    return False
