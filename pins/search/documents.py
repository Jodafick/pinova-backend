"""Construction des documents Typesense depuis les modèles Django."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import Profile
from pins.models import Board, Pin


def pin_to_typesense_doc(pin: Pin) -> dict:
    hashtags = list(pin.hashtags.values_list('name', flat=True))
    author_profile = getattr(pin.author, 'profile', None)
    created_ts = int((pin.created_at or timezone.now()).timestamp())
    return {
        'id': str(pin.pk),
        'slug': pin.slug or '',
        'title': pin.title or '',
        'description': (pin.description or '')[:1000],
        'author_username': pin.author.username,
        'author_id': pin.author_id,
        'hashtags': hashtags,
        'visibility': pin.visibility,
        'moderation_hidden': bool(pin.moderation_hidden),
        'author_private_profile': bool(getattr(author_profile, 'private_profile', False)),
        'created_at': created_ts,
    }


def pin_searchable(pin: Pin) -> bool:
    if pin.moderation_hidden:
        return False
    if pin.visibility == Pin.VISIBILITY_PRIVATE:
        return False
    if pin.is_story and pin.story_ephemeral:
        return False
    now = timezone.now()
    if pin.scheduled_publish_at and pin.scheduled_publish_at > now:
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
