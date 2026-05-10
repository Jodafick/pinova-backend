"""Résolution d'utilisateur pour les invitations (pseudo insensible à la casse ou nom affiché exact)."""

from __future__ import annotations

from django.contrib.auth.models import User


def _candidate_payload(user: User) -> dict[str, str]:
    p = user.profile
    dn = (p.display_name or '').strip() or user.username
    return {'username': user.username, 'display_name': dn}


def resolve_user_for_invite_identifier(raw: str) -> tuple[User | None, str | None, list[dict[str, str]]]:
    """
    Retourne (user, err, candidates) où err est None en cas de succès, sinon :
    'required', 'not_found', 'ambiguous_display_name'

    Si err == 'ambiguous_display_name', candidates est la liste des comptes concernés
    (username + display_name) pour affichage / choix côté client.
    """
    needle = (raw or '').strip().lstrip('@')
    if len(needle) < 2:
        return None, 'required', []
    user = User.objects.select_related('profile').filter(username__iexact=needle).first()
    if user:
        return user, None, []
    matches = list(
        User.objects.select_related('profile')
        .filter(profile__display_name__iexact=needle)
        .order_by('username')
    )
    if len(matches) == 1:
        return matches[0], None, []
    if len(matches) > 1:
        return None, 'ambiguous_display_name', [_candidate_payload(u) for u in matches]
    return None, 'not_found', []
