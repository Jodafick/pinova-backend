from __future__ import annotations

from django.contrib.auth.models import User

from notifications.notification_i18n import create_localized_notification

from .referral_notify_throttle import allow_referral_rank_notification


def notify_referrer_filleul_validated(*, referrer: User, referee_username: str, contest_key: str) -> None:
    create_localized_notification(
        recipient=referrer,
        notification_type='system',
        title_fr='Nouveau filleul validé',
        message_fr=f'{referee_username} a validé son inscription grâce à votre parrainage ({contest_key}).',
        action_url='/referrals/contest',
        metadata={'kind': 'referral_filleul_validated', 'contest_key': contest_key},
    )


def notify_referrer_reward_unlocked(*, referrer: User, contest_key: str, message_fr: str) -> None:
    create_localized_notification(
        recipient=referrer,
        notification_type='system',
        title_fr='Progression parrainage',
        message_fr=message_fr,
        action_url='/referrals/contest',
        metadata={'kind': 'referral_reward', 'contest_key': contest_key},
    )


def maybe_notify_referral_leaderboard_rank(
    *,
    recipient: User,
    contest_key: str,
    prev_rank: int | None,
    new_rank: int | None,
    total_score: float,
    contest_settings,
) -> None:
    """Réutilise notify_top_100 / notify_top_10 / notify_winner ; jalons seulement (anti-spam)."""
    if new_rank is None:
        return
    p = prev_rank if (prev_rank is not None and prev_rank > 0) else 9999
    n = new_rank
    entered_top100 = n <= 100 and p > 100
    entered_top10 = n <= 10 and p > 10
    became_first = n == 1 and p > 1
    if not (entered_top100 or entered_top10 or became_first):
        return
    if entered_top100 and not getattr(contest_settings, 'notify_top_100', True):
        return
    if entered_top10 and not getattr(contest_settings, 'notify_top_10', True):
        return
    if became_first and not getattr(contest_settings, 'notify_winner', True):
        return

    if not allow_referral_rank_notification(
        recipient_id=recipient.id,
        contest_key=contest_key,
        prev_rank=prev_rank,
        new_rank=new_rank,
    ):
        return

    if became_first:
        tit, msg = 'Première place parrainage', f'Vous êtes 1er du classement parrainage ({contest_key}) !'
    elif entered_top10:
        tit, msg = 'Top 10 parrainage', f'Vous entrez dans le top 10 du parrainage ({contest_key}). Rang : {new_rank}.'
    elif entered_top100:
        tit, msg = 'Top 100 parrainage', f'Vous entrez dans le top 100 du parrainage ({contest_key}). Rang : {new_rank}.'
    else:
        tit, msg = 'Classement parrainage', f'Nouveau rang : {new_rank} (score {total_score:.1f}).'

    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr=tit,
        message_fr=msg,
        action_url='/referrals/contest',
        metadata={
            'kind': 'referral_contest_rank',
            'contest_key': contest_key,
            'rank': new_rank,
            'previous_rank': prev_rank,
            'total_score': total_score,
        },
    )


def notify_referral_contest_month_closed(*, recipient: User, contest_key: str, rank: int, score: float) -> None:
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr='Concours parrainage terminé',
        message_fr=f'Le mois {contest_key} est clos. Votre classement final : #{rank} ({score:.1f} pts).',
        action_url='/referrals/contest/archives',
        metadata={'kind': 'referral_contest_closed', 'contest_key': contest_key, 'rank': rank},
    )


def notify_referral_new_month(*, recipient: User, new_contest_key: str) -> None:
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr='Nouveau mois parrainage',
        message_fr=f'Le concours parrainage {new_contest_key} a commencé. Bonne chance !',
        action_url='/referrals/contest',
        metadata={
            'kind': 'referral_contest_new_month',
            'contest_key': new_contest_key,
            'delivery_mode': 'ws_and_push',
        },
    )


def notify_referral_contest_new_month_participants(contest, *, limit: int = 800) -> None:
    """Notifie les parrains actifs du mois précédent (best-effort)."""
    from contests.models import ContestSettings

    from .models import ReferrerReferralScore

    prev = (
        ContestSettings.objects.filter(end_at__lte=contest.start_at)
        .exclude(pk=contest.pk)
        .order_by('-end_at')
        .first()
    )
    if not prev:
        return
    referrer_ids = list(
        ReferrerReferralScore.objects.filter(contest=prev, total_score__gt=0)
        .values_list('referrer_id', flat=True)
        .distinct()[: max(1, limit)]
    )
    if not referrer_ids:
        return
    for user in User.objects.filter(pk__in=referrer_ids, is_active=True).only('id'):
        notify_referral_new_month(recipient=user, new_contest_key=contest.contest_key)
