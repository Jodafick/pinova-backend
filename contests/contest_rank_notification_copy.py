"""
Copy concours (FR canonique) — ton social / compétition, variantes aléatoires.

Titres et corps courts (mobile-first). Traduction destinataire via notification_i18n.
"""

from __future__ import annotations

import random

from django.contrib.auth.models import User

NOTIF_TITLE_MAX = 120
NOTIF_BODY_MAX = 255
_TITLE_SOFT_MAX = 48
_BODY_SOFT_MAX = 178


def _short(s: str, n: int) -> str:
    s = (s or '').strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + '…'


def _display_name(user: User) -> str:
    """display_name profil > prénom > username (jamais froid / technique)."""
    try:
        prof = getattr(user, 'profile', None)
        if prof is not None:
            dn = (getattr(prof, 'display_name', None) or '').strip()
            if dn:
                return dn
    except Exception:
        pass
    fn = (user.first_name or '').strip()
    if fn:
        return fn
    return (user.username or 'toi').strip() or 'toi'


def _pick(pool: list[tuple[str, str]]) -> tuple[str, str]:
    return random.choice(pool)


def _momentum_clause(
    *,
    likes_d: int,
    views_d: int,
    comments_d: int,
    views_total: int | None,
) -> str:
    if views_total is not None and views_total >= 2500 and random.random() < 0.35:
        return random.choice(
            [
                'Les vues s’accumulent sur ton foto 👀 ',
                'Ton foto attire du monde 🔥 ',
                'Beaucoup d’œil sur ce foto en ce moment ⚡ ',
            ]
        )
    if views_total is not None and views_total >= 800 and random.random() < 0.28:
        return random.choice(
            [
                'Le buzz monte doucement 📈 ',
                'Ton foto circule bien 👀 ',
            ]
        )
    bump = likes_d + views_d + comments_d
    if bump <= 0:
        return ''
    if likes_d >= 1 and random.random() < 0.4:
        return random.choice(
            [
                'Un like de plus, ça pousse 🔥 ',
                'Les cœurs arrivent ⚡ ',
            ]
        )
    if views_d >= 1 and random.random() < 0.45:
        return random.choice(
            [
                'Encore des vues qui rentrent 👀 ',
                'Ton foto se fait voir 📈 ',
            ]
        )
    if comments_d >= 1 and random.random() < 0.5:
        return random.choice(
            [
                'Un commentaire vient de booster le foto 💬 ',
                'La convo s’anime sur ton foto 🔥 ',
            ]
        )
    if bump >= 1 and random.random() < 0.25:
        return random.choice(['Ça bouge côté interactions ⚡ ', 'Le momentum suit 📈 '])
    return ''


def _social_cta() -> str:
    if random.random() > 0.55:
        return ''
    return ' ' + random.choice(
        [
            'Fais tourner ton foto, ça aide 🔥',
            'Partage-le : plus il circule, plus ça grimpe 🚀',
            'Envoie-le à ton crew pour liker et commenter 👀',
            'Tes potes peuvent te propulser vers le haut ⚡',
            'Ne lâche pas les partages — la concurrence dort jamais 🏆',
            'Un story ou un lien en plus = plus de chances 👀',
            'Plus ton foto voyage, plus le classement te suit 🔥',
        ]
    )


def _fmt_pin(pin_title: str) -> str:
    return _short(pin_title, 52)


def build_contest_display_rank_notification_fr(
    *,
    recipient: User,
    pin_title: str,
    prev_rank: int | None,
    new_rank: int | None,
    likes_delta: int = 0,
    views_delta: int = 0,
    comments_delta: int = 0,
    views_total: int | None = None,
) -> tuple[str, str]:
    """
    Retourne (title_fr, message_fr). Rang = place affichée (meilleur foto / créateur).
    Plusieurs variantes aléatoires par scénario.
    """
    name = _display_name(recipient)
    foto = _fmt_pin(pin_title)
    prev_s = '—' if prev_rank is None else str(prev_rank)
    new_s = '—' if new_rank is None else str(new_rank)

    mom = _momentum_clause(
        likes_d=likes_delta,
        views_d=views_delta,
        comments_d=comments_delta,
        views_total=views_total,
    )
    cta = _social_cta()

    if new_rank is None:
        tit, body = _pick(
            [
                ('Le mois bouge 👀', f'{name}, ton foto « {pin} » vient de prendre un coup de boost.'),
                ('Classement en mouvement ⚡', f'{name}, « {pin} » : le concours accélère autour de toi.'),
            ]
        )
        body_full = (mom + body + cta).replace('  ', ' ').strip()
        return _short(tit, _TITLE_SOFT_MAX)[:NOTIF_TITLE_MAX], _short(body_full, _BODY_SOFT_MAX)[:NOTIF_BODY_MAX]

    prev_in = prev_rank is not None and prev_rank <= 3
    new_in = new_rank <= 3
    improved = prev_rank is None or new_rank < prev_rank
    worse = prev_rank is not None and new_rank > prev_rank

    # CAS C — sortie du top 3
    if prev_in and not new_in:
        tit, body = _pick(
            [
                (
                    '⚠️ Le podium s’éloigne',
                    f'{name}, « {pin} » n’est plus top 3 pour l’instant (n°{new_s}, tu étais n°{prev_s}). Relance les partages et reviens plus fort 👀',
                ),
                (
                    'Ça glisse 👀',
                    f'{name}, ton foto « {pin} » a reculé au n°{new_s} (tu étais n°{prev_s}). La compèt’ accélère — motive ton squad 🔥',
                ),
                (
                    'Pas le moment de lâcher',
                    f'{name}, « {pin} » quitte le top 3 (n°{new_s}). Avant : n°{prev_s}. Enchaîne les partages pour remonter 🚀',
                ),
                (
                    'Le classement t’a rattrapé',
                    f'{name}, « {pin} » est au n°{new_s} (ex n°{prev_s}). Tes potes peuvent t’aider à remonter vite ⚡',
                ),
                (
                    'Ouch — top 3 perdu',
                    f'{name}, « {pin} » passe n°{new_s} (tu étais n°{prev_s}). Plus ton foto circule, plus tu reviens 📈',
                ),
                (
                    'Urgence concours 🏆',
                    f'{name}, hors podium pour « {pin} » (n°{new_s}, avant n°{prev_s}). Fais tourner le foto, la remontada est possible 🔥',
                ),
            ]
        )

    # CAS A — podium interne : montée
    elif new_in and prev_in and improved:
        if new_rank == 1 and prev_rank is not None and prev_rank > 1:
            tit, body = _pick(
                [
                    (
                        '🥇 Tu prends la tête !',
                        f'{name}, « {pin} » vient de passer n°1 🔥 Continue à le partager pour garder le podium.',
                    ),
                    (
                        '👑 N°1 — c’est toi',
                        f'{name}, « {pin} » décroche la tête (ex n°{prev_s}). Tes potes peuvent t’aider à rester en haut 🏆',
                    ),
                    (
                        '🚀 Tu passes devant tout le monde',
                        f'{name}, « {pin} » au sommet (avant n°{prev_s}). Ne lâche pas les partages, le mois continue ⚡',
                    ),
                    (
                        '🔥 Le podium est à toi',
                        f'{name}, n°1 avec « {pin} » (tu étais n°{prev_s}). Fais tourner le foto pour rester intouchable 👀',
                    ),
                    (
                        '🏆 Exploit',
                        f'{name}, « {pin} » en tête ! Avant : n°{prev_s}. Plus il buzz, plus tu dors tranquille 🔥',
                    ),
                    (
                        '👀 Tout le monde te regarde',
                        f'{name}, « {pin} » au n°1 depuis n°{prev_s}. Demande des likes à ton crew pour verrouiller 🚀',
                    ),
                ]
            )
        else:
            tit, body = _pick(
                [
                    (
                        '🚀 Explosion vers le haut',
                        f'{name}, « {pin} » grimpe au n°{new_s} (avant n°{prev_s}). Le mois est chaud — ne ralentis pas ⚡',
                    ),
                    (
                        '👀 Tout le monde te regarde',
                        f'{name}, « {pin} » au n°{new_s} (ex n°{prev_s}). Tes amis peuvent t’aider à verrouiller la place 🏆',
                    ),
                    (
                        '🏆 Domination en cours',
                        f'{name}, « {pin} » monte au n°{new_s} depuis n°{prev_s}. Partage-le : la concurrence ne dort pas 🔥',
                    ),
                    (
                        '⚡ Ça monte vite',
                        f'{name}, n°{new_s} pour « {pin} » (tu étais n°{prev_s}). Plus il circule, plus tu sécurises 📈',
                    ),
                    (
                        '🥈 Place de vice-champion',
                        f'{name}, « {pin} » au n°{new_s} (avant n°{prev_s}). Fais tourner le foto pour viser encore plus haut 🚀',
                    ),
                    (
                        '🥉 Podium assuré',
                        f'{name}, « {pin} » tient le n°{new_s} (ex n°{prev_s}). Garde le momentum avec des partages 👀',
                    ),
                    (
                        '🔥 Tu chauffes le classement',
                        f'{name}, « {pin} » passe n°{new_s} (avant n°{prev_s}). Demande un max de likes autour de toi ⚡',
                    ),
                    (
                        '📈 Belle montée',
                        f'{name}, « {pin} » au n°{new_s} depuis n°{prev_s}. Le podium brûle — motive ton squad 🔥',
                    ),
                ]
            )

    # Podium interne : descente
    elif new_in and prev_in and worse:
        tit, body = _pick(
            [
                (
                    '⚡ Tu recules d’un cran',
                    f'{name}, « {pin} » au n°{new_s} (tu étais n°{prev_s}). Le podium bouge — relance les partages 👀',
                ),
                (
                    '👀 Ils te collent au classement',
                    f'{name}, « {pin} » passe n°{new_s} (avant n°{prev_s}). Fais tourner ton foto pour reprendre l’avantage 🔥',
                ),
                (
                    '🏆 Toujours podium',
                    f'{name}, « {pin} » reste dans le top 3 au n°{new_s} (ex n°{prev_s}). Ne lâche pas, le mois est long ⚡',
                ),
                (
                    '🔥 Ça serré au sommet',
                    f'{name}, n°{new_s} pour « {pin} » (tu étais n°{prev_s}). Tes amis peuvent liker et commenter pour toi 🚀',
                ),
                (
                    '📉 Petit recul',
                    f'{name}, « {pin} » au n°{new_s} depuis n°{prev_s}. Partage-le : chaque vue compte 👀',
                ),
                (
                    '⚠️ Garde ta place',
                    f'{name}, « {pin} » au n°{new_s} (avant n°{prev_s}). La concurrence accélère — motive ton crew 🔥',
                ),
            ]
        )

    # CAS B — entrée dans le top 3 depuis l’extérieur
    elif new_in and (not prev_in or prev_rank is None):
        prev_bit = f' (avant n°{prev_s})' if prev_rank is not None else ''
        tit, body = _pick(
            [
                (
                    '🚀 Tu entres au podium',
                    f'{name}, « {pin} » débarque en n°{new_s}{prev_bit}. Le buzz peut exploser — fais tourner 🔥',
                ),
                (
                    '🔥 Top 3 touché',
                    f'{name}, « {pin} » est n°{new_s}{prev_bit}. Partage-le à fond, le N°1 est proche 👀',
                ),
                (
                    '👀 Le podium te tend les bras',
                    f'{name}, « {pin} » grimpe en n°{new_s}{prev_bit}. Tes potes peuvent te propulser encore 🚀',
                ),
                (
                    '⚡ Percée massive',
                    f'{name}, n°{new_s} pour « {pin} »{prev_bit}. Ne ralentis pas les partages 🏆',
                ),
                (
                    '🏆 Incroyable remontée',
                    f'{name}, « {pin} » au top 3 (n°{new_s}){prev_bit}. Plus il circule, plus tu domines 🔥',
                ),
                (
                    '📈 Ça part en viral',
                    f'{name}, « {pin} » entre au n°{new_s}{prev_bit}. Demande des likes à ton squad ⚡',
                ),
                (
                    '🔥 Le mois te sourit',
                    f'{name}, podium : « {pin} » en n°{new_s}{prev_bit}. Garde le rythme côté partages 👀',
                ),
            ]
        )

    # CAS D — progression hors top 3
    elif improved:
        tit, body = _pick(
            [
                (
                    '🚀 Grosse remontée',
                    f'{name}, « {pin} » grimpe au n°{new_s} (avant n°{prev_s}). Les interactions s’accélèrent ⚡',
                ),
                (
                    '📈 Ça monte pour toi',
                    f'{name}, n°{new_s} avec « {pin} » (ex n°{prev_s}). Partage-le : le podium se rapproche 👀',
                ),
                (
                    '🔥 Tu grappilles des places',
                    f'{name}, « {pin} » passe n°{new_s} (tu étais n°{prev_s}). Tes amis peuvent t’aider à monter 🚀',
                ),
                (
                    '⚡ Momentum',
                    f'{name}, « {pin} » au n°{new_s} depuis n°{prev_s}. Plus ton foto voyage, plus ça grimpe 🔥',
                ),
                (
                    '👀 On te voit monter',
                    f'{name}, n°{new_s} pour « {pin} » (avant n°{prev_s}). Fais tourner le foto, la compèt’ est vivante 🏆',
                ),
                (
                    '🏆 Belle avancée',
                    f'{name}, « {pin} » gagne des places : n°{new_s} (ex n°{prev_s}). Ne lâche pas les partages ⚡',
                ),
                (
                    '🔥 Le classement te suit',
                    f'{name}, « {pin} » au n°{new_s} (tu étais n°{prev_s}). Demande des coms et des likes autour de toi 👀',
                ),
                (
                    '🚀 Tu passes du monde',
                    f'{name}, « {pin} » dépasse du monde : n°{new_s} (avant n°{prev_s}). Continue à faire tourner 🔥',
                ),
            ]
        )

    # CAS E — chute hors top 3
    elif worse:
        tit, body = _pick(
            [
                (
                    '👀 Petit coup de frein',
                    f'{name}, « {pin} » au n°{new_s} (tu étais n°{prev_s}). Relance les partages, le mois continue 🚀',
                ),
                (
                    '⚡ Ça descend',
                    f'{name}, n°{new_s} pour « {pin} » (avant n°{prev_s}). Tes potes peuvent liker pour te refaire 📈',
                ),
                (
                    '🔥 Pas le moment de dormir',
                    f'{name}, « {pin} » recule au n°{new_s} (ex n°{prev_s}). Fais tourner le foto pour remonter 👀',
                ),
                (
                    '🏆 Rattrape-les',
                    f'{name}, « {pin} » au n°{new_s} depuis n°{prev_s}. Plus il circule, plus tu reviens 🔥',
                ),
                (
                    '📉 Le classement bouge',
                    f'{name}, n°{new_s} avec « {pin} » (tu étais n°{prev_s}). Motive ton squad sur les interactions ⚡',
                ),
                (
                    '👀 Rien n’est joué',
                    f'{name}, « {pin} » au n°{new_s} (avant n°{prev_s}). Partage-le : la remontada est possible 🚀',
                ),
            ]
        )

    else:
        tit, body = _pick(
            [
                ('Fotoce concours 🏆', f'{name}, « {pin} » : n°{new_s} affiché. Reste dans le game 👀'),
                ('Classement live ⚡', f'{name}, « {pin} » se place n°{new_s}. Fais tourner pour monter 🔥'),
            ]
        )

    body_full = (mom + body + cta).replace('  ', ' ').strip()
    return _short(tit, _TITLE_SOFT_MAX)[:NOTIF_TITLE_MAX], _short(body_full, _BODY_SOFT_MAX)[:NOTIF_BODY_MAX]
