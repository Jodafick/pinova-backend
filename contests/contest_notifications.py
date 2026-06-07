from __future__ import annotations

from django.contrib.auth.models import User

from contests.models import ContestSettings, PinContestScore
from notifications.notification_i18n import create_localized_notification


def notify_contest_new_month(*, recipient: User, contest_key: str) -> None:
    create_localized_notification(
        recipient=recipient,
        notification_type='system',
        title_fr='Nouveau concours mensuel',
        message_fr=f'Le concours {contest_key} a commencé. Publiez vos meilleurs pins !',
        action_url='/contest/live',
        metadata={
            'kind': 'contest_new_month',
            'contest_key': contest_key,
            'delivery_mode': 'ws_and_push',
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
        PinContestScore.objects.filter(contest=prev)
        .values_list('creator_id', flat=True)
        .distinct()[: max(1, limit)]
    )
    if not creator_ids:
        return
    for user in User.objects.filter(pk__in=creator_ids, is_active=True).only('id'):
        notify_contest_new_month(recipient=user, contest_key=contest.contest_key)
