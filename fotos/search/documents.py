"""Construction des documents Typesense depuis les modèles Django."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import Profile
from fotos.models import Board, Foto


def pin_to_typesense_doc(foto: Foto) -> dict:
    hashtags = list(pin.hashtags.values_list('name', flat=True))
    author_profile = getattr(pin.author, 'profile', None)
    created_ts = int((pin.created_at or timezone.now()).timestamp())
    return {
        'id': str(pin.pk),
        'slug': foto.slug or '',
        'title': foto.title or '',
        'description': (pin.description or '')[:1000],
        'author_username': foto.author.username,
        'author_id': foto.author_id,
        'hashtags': hashtags,
        'visibility': foto.visibility,
        'moderation_hidden': bool(pin.moderation_hidden),
        'author_private_profile': bool(getattr(author_profile, 'private_profile', False)),
        'created_at': created_ts,
    }


def pin_searchable(foto: Foto) -> bool:
    if foto.moderation_hidden:
        return False
    if foto.visibility == Foto.VISIBILITY_PRIVATE:
        return False
    if foto.is_story and foto.story_ephemeral:
        return False
    now = timezone.now()
    if foto.scheduled_publish_at and foto.scheduled_publish_at > now:
        return False
    return True


def user_to_typesense_doc(user: User) -> dict | None:
    profile = getattr(user, 'profile', None)
    if profile is None:
        return None
    return {
        'id': str(user.pk),
        'username': user.username,
        'display_name': (profile.display_name or user.username).strip() or user.username,
        'discoverable_profile': bool(profile.discoverable_profile),
        'avatar_color': profile.avatar_color or 'bg-neutral-400',
    }


def board_to_typesense_doc(board: Board) -> dict:
    collaborator_ids = list(board.collaborators.values_list('pk', flat=True))
    created_ts = int((board.created_at or timezone.now()).timestamp())
    return {
        'id': str(board.pk),
        'name': board.name or '',
        'description': (board.description or '')[:1000],
        'owner_username': board.user.username if board.user_id else '',
        'owner_id': board.user_id,
        'is_private': bool(board.is_private),
        'collaborator_ids': collaborator_ids,
        'created_at': created_ts,
    }
