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


def viewer_hides_sensitive_pins(request) -> bool:
    """Préférence profil « ne pas voir » les médias signalés sensibles (majeurs vérifiés uniquement)."""
    if not request.user.is_authenticated:
        return False
    profile = getattr(request.user, 'profile', None)
    if not profile_is_verified_adult(profile):
        return False
    return bool(getattr(profile, 'hide_sensitive_pins', False))


def sensitive_pin_allowed_for_viewer(pin: Pin, request) -> bool:
    """Pins `media_sensitive_blur` : réservés aux adultes vérifiés ; l’auteur voit toujours le sien."""
    if not getattr(pin, 'media_sensitive_blur', False):
        return True
    user = request.user if request.user.is_authenticated else None
    if user and user.id == pin.author_id:
        return True
    if viewer_hides_sensitive_pins(request):
        return False
    return viewer_is_verified_adult(request)


def sensitive_pins_query_filter(request):
    """Filtre queryset : masque les pins sensibles pour mineurs / anonymes (sauf auteur)."""
    if viewer_hides_sensitive_pins(request):
        user = request.user if request.user.is_authenticated else None
        if user:
            return Q(media_sensitive_blur=False) | Q(author=user)
        return Q(media_sensitive_blur=False)
    if viewer_is_verified_adult(request):
        return Q()
    user = request.user if request.user.is_authenticated else None
    if user:
        return Q(media_sensitive_blur=False) | Q(author=user)
    return Q(media_sensitive_blur=False)


def count_pins_visible_on_profile(author_user, request) -> int:
    """
    Nombre de pins d'un créateur visibles pour le visiteur, aligné sur
    PinViewSet.get_queryset avec le filtre ?author=<username> (liste profil).
    """
    queryset = Pin.objects.filter(author=author_user).select_related('author', 'author__profile')
    sched = Q(scheduled_publish_at__isnull=True) | Q(scheduled_publish_at__lte=timezone.now())
    now_tz = timezone.now()
    story_q = (
        Q(is_story=False)
        | Q(is_story=True, story_ephemeral=False)
        | Q(is_story=True, story_ephemeral=True, story_expires_at__gt=now_tz)
    )
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    if user is not None:
        story_q |= Q(is_story=True, author=user)


    if not user:
        core = (
            Q(visibility=Pin.VISIBILITY_PUBLIC, author__profile__private_profile=False)
            & sched
            & story_q
            & Q(moderation_hidden=False)
        )
        qs = queryset.filter(core)
        qs = qs.filter(sensitive_pins_query_filter(request))
        qs = qs.exclude(Q(is_story=True, story_ephemeral=True))
        return qs.count()

    my_profile = user.profile
    visibility_q = (
        Q(visibility=Pin.VISIBILITY_PUBLIC, author__profile__private_profile=False)
        | Q(author=user)
        | Q(visibility=Pin.VISIBILITY_FOLLOWERS, author__profile__followers=my_profile)
        | Q(author__profile__private_profile=True, author__profile__followers=my_profile)
    )
    core = visibility_q & story_q & (sched | Q(author=user))
    qs = queryset.filter(core).distinct()
    qs = qs.filter(sensitive_pins_query_filter(request))
    qs = qs.exclude(Q(moderation_hidden=True) & ~Q(author=user))
    qs = qs.exclude(Q(is_story=True, story_ephemeral=True))
    return qs.count()


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
    if (
        pin.is_story
        and pin.story_ephemeral
        and pin.story_expires_at
        and pin.story_expires_at <= now
    ):
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
