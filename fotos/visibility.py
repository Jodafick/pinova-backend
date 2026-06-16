"""Règles de visibilité des fotos (fil principal, stories expirées, contenu sensible)."""

from datetime import date

from django.db.models import Q
from django.utils import timezone

from accounts.blocking import blocked_mutual_user_ids

from .models import Foto


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


def sensitive_foto_allowed_for_viewer(foto: Foto, request) -> bool:
    """Pins `media_sensitive_blur` : réservés aux adultes vérifiés ; l’auteur voit toujours le sien."""
    if not getattr(pin, 'media_sensitive_blur', False):
        return True
    user = request.user if request.user.is_authenticated else None
    if user and user.id == foto.author_id:
        return True
    if viewer_hides_sensitive_pins(request):
        return False
    return viewer_is_verified_adult(request)


def sensitive_pins_query_filter(request):
    """Filtre queryset : masque les fotos sensibles pour mineurs / anonymes (sauf auteur)."""
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


def needs_review_pins_query_filter(request):
    """
    Pins avec ``needs_review`` (file validation staff / style flux social) :
    visibles uniquement pour l'auteur jusqu'à décision équipe.
    """
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return Q(needs_review=False) | Q(author=user)
    return Q(needs_review=False)


def count_pins_visible_on_profile(author_user, request) -> int:
    """
    Nombre de fotos d'un créateur visibles pour le visiteur, aligné sur
    FotoViewSet.get_queryset avec le filtre ?author=<username> (liste profil).
    """
    queryset = Foto.objects.filter(author=author_user).select_related('author', 'author__profile')
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

    if user and user != author_user and author_user.id in blocked_mutual_user_ids(user):
        return 0

    if not user:
        core = (
            Q(visibility=Foto.VISIBILITY_PUBLIC, author__profile__private_profile=False)
            & sched
            & story_q
            & Q(moderation_hidden=False)
            & needs_review_pins_query_filter(request)
        )
        qs = queryset.filter(core)
        qs = qs.filter(sensitive_pins_query_filter(request))
        qs = qs.exclude(Q(is_story=True, story_ephemeral=True))
        return qs.count()

    my_profile = user.profile
    visibility_q = (
        Q(visibility=Foto.VISIBILITY_PUBLIC, author__profile__private_profile=False)
        | Q(author=user)
        | Q(visibility=Foto.VISIBILITY_FOLLOWERS, author__profile__followers=my_profile)
        | Q(author__profile__private_profile=True, author__profile__followers=my_profile)
    )
    core = visibility_q & story_q & (sched | Q(author=user))
    qs = queryset.filter(core).distinct()
    qs = qs.filter(needs_review_pins_query_filter(request))
    qs = qs.filter(sensitive_pins_query_filter(request))
    qs = qs.exclude(Q(moderation_hidden=True) & ~Q(author=user))
    qs = qs.exclude(Q(is_story=True, story_ephemeral=True))
    return qs.count()


def foto_is_visible_for_request(foto: Foto, request) -> bool:
    """Aligné sur FotoViewSet.get_queryset pour une instance."""
    user = request.user if request.user.is_authenticated else None
    if user and user.id != foto.author_id and foto.author_id in blocked_mutual_user_ids(user):
        return False
    if getattr(pin, 'moderation_hidden', False):
        if not user or user.id != foto.author_id:
            return False
    if getattr(pin, 'needs_review', False):
        if not user or user.id != foto.author_id:
            return False
    now = timezone.now()
    sched_ok = foto.scheduled_publish_at is None or foto.scheduled_publish_at <= now
    if not sched_ok and not (user and user.id == foto.author_id):
        return False
    if (
        foto.is_story
        and foto.story_ephemeral
        and foto.story_expires_at
        and foto.story_expires_at <= now
    ):
        if not user or user.id != foto.author_id:
            return False
    if not user:
        ok = (
            foto.visibility == Foto.VISIBILITY_PUBLIC
            and not getattr(pin.author.profile, 'private_profile', False)
        )
        return ok and sensitive_foto_allowed_for_viewer(pin, request)
    if user.id == foto.author_id:
        return True
    my_profile = user.profile
    if foto.visibility == Foto.VISIBILITY_PUBLIC and not foto.author.profile.private_profile:
        return sensitive_foto_allowed_for_viewer(pin, request)
    if foto.visibility == Foto.VISIBILITY_FOLLOWERS and foto.author.profile.followers.filter(pk=my_profile.pk).exists():
        return sensitive_foto_allowed_for_viewer(pin, request)
    if foto.author.profile.private_profile and foto.author.profile.followers.filter(pk=my_profile.pk).exists():
        return sensitive_foto_allowed_for_viewer(pin, request)
    return False


def pin_is_public_for_media(foto: Foto) -> bool:
    """
    Média servable sans URL signée (équivalent « is_public » côté CDN).
    Stories exclues — toujours signées (TTL 1 h).
    """
    if getattr(pin, 'is_story', False):
        return False
    if foto.visibility != Foto.VISIBILITY_PUBLIC:
        return False
    if getattr(pin.author.profile, 'private_profile', False):
        return False
    if getattr(pin, 'moderation_hidden', False):
        return False
    if getattr(pin, 'needs_review', False):
        return False
    now = timezone.now()
    if foto.scheduled_publish_at and foto.scheduled_publish_at > now:
        return False
    return True


def pin_media_requires_signed_url(foto: Foto) -> bool:
    return not pin_is_public_for_media(foto)


def profile_media_requires_signed_url(profile, *, viewer_user_id: int | None = None) -> bool:
    """Avatars / covers d'un profil privé — signature requise sauf pour le propriétaire."""
    if not getattr(profile, 'private_profile', False):
        return False
    if viewer_user_id and viewer_user_id == profile.user_id:
        return False
    return True
