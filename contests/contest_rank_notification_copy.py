"""Textes FR canoniques (traduits côté destinataire via notification_i18n)."""

from __future__ import annotations

from django.contrib.auth.models import User

NOTIF_TITLE_MAX = 120
NOTIF_BODY_MAX = 255


def _short(s: str, n: int) -> str:
    s = (s or '').strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + '…'


def _display_name(user: User) -> str:
    fn = (user.first_name or '').strip()
    return fn or user.username


def _podium_intro_fr(new_rank: int) -> tuple[str, str]:
    if new_rank == 1:
        return '🥇 1ère place du concours', 'est en tête du classement — félicitations.'
    if new_rank == 2:
        return '🥈 2e place — superbe', 'grimpe sur la 2e marche. Continue comme ça.'
    return '🥉 3e place — podium', 'tient la 3e place. Encore un effort pour viser plus haut.'


def build_contest_display_rank_notification_fr(
    *,
    recipient: User,
    pin_title: str,
    prev_rank: int | None,
    new_rank: int | None,
) -> tuple[str, str]:
    """Retourne (title_fr, body_fr). `pin_title` = meilleur pin affiché au classement."""
    name = _display_name(recipient)
    title_safe = _short(pin_title, 72)
    prev_s = '—' if prev_rank is None else str(prev_rank)
    new_s = '—' if new_rank is None else str(new_rank)

    if new_rank is None:
        tit = 'Classement concours'
        body = f'{name}, mise à jour de classement (« {title_safe} »).'
        return tit[:NOTIF_TITLE_MAX], body[:NOTIF_BODY_MAX]

    prev_in = prev_rank is not None and prev_rank <= 3
    new_in = new_rank <= 3

    improved = prev_rank is None or new_rank < prev_rank
    worse = prev_rank is not None and new_rank > prev_rank

    # Hors podium → perd le podium
    if prev_in and not new_in:
        tit = 'Hors podium — garde le cap'
        body = f'{name}, « {title_safe} » passe #{new_s} (#{prev_s}). Chaque coup de pouce rapproche du top 3.'

    # Entrée ou progression sur podium (depuis hors top 3 ou première mesure)
    elif new_in and (not prev_in or prev_rank is None):
        tit, frag = _podium_intro_fr(new_rank)
        body = f'{name}, « {title_safe} » {frag}'

    # Toujours sur podium mais recul (#1→#2, #2→#3…)
    elif new_in and prev_in and worse:
        tit = f'Toujours sur le podium (#{new_s})'
        body = f'{name}, « {title_safe} » (#{prev_s}→#{new_s}). Le classement bouge vite — reste focus.'

    # Amélioration hors podium
    elif improved:
        tit = 'Tu grimpes au classement'
        body = f'{name}, place affichée #{new_s} (avant #{prev_s}). « {title_safe} » gagne du terrain.'

    # Recul hors podium
    elif worse:
        tit = 'Petit recul au classement'
        body = f'{name}, place affichée #{new_s} (tu étais #{prev_s}). « {title_safe} » — chaque interaction compte, courage.'

    else:
        tit = 'Classement concours'
        body = f'{name}, « {title_safe} » : #{new_s}e place affichée.'

    return tit[:NOTIF_TITLE_MAX], body[:NOTIF_BODY_MAX]
