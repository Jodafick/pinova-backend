"""Blocages utilisateur : masquage mutuel du contenu (pins, profils, notifications, etc.)."""

from __future__ import annotations

from django.db.models import Q

from django.contrib.auth.models import User


def blocked_mutual_user_ids(viewer: User) -> frozenset[int]:
    """
    Identifiants des comptes avec lesquels `viewer` ne doit plus interagir ni voir le contenu
    (je les ai bloqués ou ils m'ont bloqué).
    """
    if not getattr(viewer, 'pk', None):
        return frozenset()
    from .models import UserBlock

    i_blocked = UserBlock.objects.filter(blocker=viewer).values_list('blocked_id', flat=True)
    blocked_me = UserBlock.objects.filter(blocked=viewer).values_list('blocker_id', flat=True)
    return frozenset(i_blocked) | frozenset(blocked_me)


def users_are_mutually_blocked(a: User, b: User) -> bool:
    if not a.pk or not b.pk or a.pk == b.pk:
        return False
    return b.id in blocked_mutual_user_ids(a)


def filter_pins_exclude_blocked(queryset, request):
    """Filtre un queryset de fotos : auteurs bloqués masqués sauf mes propres fotos."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return queryset
    forb = blocked_mutual_user_ids(user)
    if not forb:
        return queryset
    uid = user.id
    return queryset.filter((~Q(author_id__in=forb)) | Q(author_id=uid))
