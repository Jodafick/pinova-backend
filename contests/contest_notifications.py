from __future__ import annotations

from django.contrib.auth.models import User

from contests.models import ContestSettings, FotoContestScore
from notifications.delivery import DELIVERY_WS_AND_PUSH, DELIVERY_WS_ONLY
from notifications.notification_i18n import create_localized_notification


def notify_contest_new_month(*, recipient: User, contest_key: str) -> None:
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr='Nouveau concours mensuel',
        message_fr=f'Le concours {contest_key} a commencé. Publiez vos meilleurs fotos !',
        action_url='/contest/live',
        metadata={
            'kind': 'contest_new_month',
            'contest_key': contest_key,
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        },
    )


def notify_contest_participants_new_month(contest: ContestSettings, *, limit: int = 800) -> None:
    """
    Notifie les créateurs ayant participé au mois précédent (best-effort, plafonné).
    """
    prev = (
        ContestSettings.objects.filter(end_at__lte=contest.start_at)
        .exclude(pk=contest.pk)
        .order_by('-end_at')
        .first()
    )
    if not prev:
        return
    creator_ids = list(
        FotoContestScore.objects.filter(contest=prev)
        .values_list('creator_id', flat=True)
        .distinct()[: max(1, limit)]
    )
    if not creator_ids:
        return
    for user in User.objects.filter(pk__in=creator_ids, is_active=True).only('id'):
        notify_contest_new_month(recipient=user, contest_key=contest.contest_key)


def notify_contest_winner(
    *,
    recipient: User,
    contest_key: str,
    rank: int,
    pin_title: str,
) -> None:
    title = 'Victoire au concours !' if rank == 1 else f'Top {rank} du concours'
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr=title,
        message_fr=(
            f'Félicitations ! Votre foto « {pin_title[:80]} » termine #{rank} '
            f'sur le concours {contest_key}.'
        ),
        action_url='/contest/live',
        metadata={
            'kind': 'contest_winner',
            'contest_key': contest_key,
            'rank': rank,
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        },
    )


def notify_contest_final_rank(
    *,
    recipient: User,
    contest_key: str,
    rank: int,
    score: float,
) -> None:
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr='Concours terminé',
        message_fr=(
            f'Le concours {contest_key} est clos. Votre meilleur classement : '
            f'#{rank} ({score:.1f} pts).'
        ),
        action_url='/contest/history',
        metadata={
            'kind': 'contest_final_rank',
            'contest_key': contest_key,
            'rank': rank,
            'score': score,
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        },
    )


def notify_foto_contest_month_closed(contest: ContestSettings, winners: list[dict], *, limit: int = 800) -> None:
    """
    Fin de mois fotos : podium + classement final pour les participants (best-effort).
    """
    winner_creator_ids = {int(w['creator_id']) for w in winners if w.get('creator_id')}

    for w in winners:
        uid = w.get('creator_id')
        if not uid:
            continue
        user = User.objects.filter(pk=uid, is_active=True).first()
        if not user:
            continue
        foto_id = w.get('foto_id')
        pin_title = 'votre foto'
        if foto_id:
            from fotos.models import Foto

            foto = Foto.objects.filter(pk=foto_id).only('title').first()
            if foto and foto.title:
                pin_title = foto.title
        notify_contest_winner(
            recipient=user,
            contest_key=contest.contest_key,
            rank=int(w.get('rank') or 1),
            pin_title=pin_title,
        )

    ordered = list(
        FotoContestScore.objects.filter(contest=contest, pin__is_story=False)
        .select_related('creator')
        .order_by('-adjusted_score', 'rank', 'foto_id')
    )
    seen: set[int] = set()
    display_rank = 0
    for row in ordered:
        cid = row.creator_id
        if cid in seen:
            continue
        seen.add(cid)
        display_rank += 1
        if display_rank > limit:
            break
        if cid in winner_creator_ids:
            continue
        user = row.creator
        if not user or not user.is_active:
            continue
        notify_contest_final_rank(
            recipient=user,
            contest_key=contest.contest_key,
            rank=display_rank,
            score=float(row.adjusted_score or 0),
        )


def contest_rank_change_metadata(
    settings: ContestSettings,
    *,
    prev_rank: int | None,
    new_rank: int | None,
) -> dict:
    """Politique livraison pour un changement de rang affiché (anti-spam + push jalons)."""
    from contests.contest_rank_notify_throttle import _is_priority_transition

    p = prev_rank if (prev_rank is not None and prev_rank > 0) else 9999
    n = new_rank if (new_rank is not None and new_rank > 0) else 9999
    entered_top100 = n <= 100 and p > 100
    entered_top10 = n <= 10 and p > 10
    became_first = n == 1 and p > 1

    if became_first and getattr(settings, 'notify_winner', True):
        return {
            'kind': 'contest_milestone_winner',
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        }
    if entered_top10 and getattr(settings, 'notify_top_10', True):
        return {
            'kind': 'contest_milestone_top10',
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        }
    if entered_top100 and getattr(settings, 'notify_top_100', True):
        return {
            'kind': 'contest_milestone_top100',
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        }
    if _is_priority_transition(prev_rank, new_rank):
        return {
            'kind': 'contest_display_rank_change',
            'delivery_mode': DELIVERY_WS_AND_PUSH,
            'in_app_toast': True,
        }
    return {
        'kind': 'contest_display_rank_change',
        'delivery_mode': DELIVERY_WS_ONLY,
        'in_app_toast': False,
    }
