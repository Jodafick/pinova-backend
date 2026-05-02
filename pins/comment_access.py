"""Règles d’accès aux commentaires (politique du pin, masquage créateur)."""

from __future__ import annotations

from .models import Pin


def comment_branch_has_hidden(comment) -> bool:
    """Masqué par le créateur ou par la modération (signalements)."""
    while comment is not None:
        if getattr(comment, 'hidden_by_owner', False) or getattr(comment, 'moderation_hidden', False):
            return True
        comment = getattr(comment, 'parent', None)
    return False


def viewer_sees_comment_content(comment, pin, request) -> bool:
    """Texte et médias visibles pour ce lecteur."""
    user = getattr(request, 'user', None) if request else None
    if user and user.is_authenticated:
        if user.id == pin.author_id:
            return True
        if user.id == comment.user_id:
            return True
    return not comment_branch_has_hidden(comment)


def user_can_comment_on_pin(pin: Pin, user) -> bool:
    """L’auteur du pin peut toujours commenter ; les autres suivent comments_policy."""
    if user and getattr(user, 'is_authenticated', False) and user.id == pin.author_id:
        return True
    if pin.comments_policy == Pin.COMMENTS_CLOSED:
        return False
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if pin.comments_policy == Pin.COMMENTS_OPEN:
        return True
    author_profile = pin.author.profile
    viewer_profile = user.profile
    return author_profile.followers.filter(pk=viewer_profile.pk).exists()
