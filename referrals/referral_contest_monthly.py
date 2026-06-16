"""
Finalisation mensuelle du concours referral (aligné sur ContestSettings / rollover fotos).
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from contests.contest_payouts import build_referral_contest_payout_payload
from contests.models import ContestSettings, ContestWinnerPayout

from .models import ReferralContestResult, ReferrerReferralScore
from .referral_contest_cache import invalidate_referral_leaderboard_cache
from .referral_contest_notifications import notify_referral_contest_month_closed

MIN_REFERRAL_LEADERBOARD_SCORE = 100.0


def finalize_referral_month_for_contest(contest: ContestSettings) -> ReferralContestResult | None:
    """
    Archive le classement referral du mois `contest` (appelé quand le mois fotos est finalisé / verrouillé).
    Idempotent.
    """
    if getattr(contest, 'end_at', None) and contest.end_at > timezone.now():
        return None
    existing = ReferralContestResult.objects.filter(contest=contest).first()
    if existing:
        winners_existing = existing.winners_json or []
        payouts_missing = not (existing.payout_json or [])
        if not payouts_missing or not winners_existing:
            return existing
        payout_json, payout_rows = build_referral_contest_payout_payload(contest, winners_existing)
        with transaction.atomic():
            existing.payout_json = payout_json
            existing.save(update_fields=['payout_json'])
            ContestWinnerPayout.objects.filter(contest=contest, source=ContestWinnerPayout.SOURCE_REFERRAL).delete()
            if payout_rows:
                ContestWinnerPayout.objects.bulk_create(payout_rows)
        return existing

    rows = list(
        ReferrerReferralScore.objects.filter(contest=contest, total_score__gte=MIN_REFERRAL_LEADERBOARD_SCORE)
        .select_related('referrer')
        .order_by('-total_score', 'referrer_id')[:500],
    )
    max_w = max(1, min(int(getattr(contest, 'max_winners', 3) or 3), 20))
    winners = []
    for i, r in enumerate(rows[:max_w], start=1):
        winners.append(
            {
                'rank': i,
                'referrer_id': r.referrer_id,
                'username': r.referrer.username,
                'score': float(r.total_score or 0.0),
            },
        )
    top_snapshot = [
        {
            'rank': i + 1,
            'referrer_id': r.referrer_id,
            'username': r.referrer.username,
            'score': float(r.total_score or 0.0),
        }
        for i, r in enumerate(rows[:200])
    ]
    stats = {
        'participants_with_score': len(rows),
        'contest_key': contest.contest_key,
    }
    payout_json, payout_rows = build_referral_contest_payout_payload(contest, winners)
    with transaction.atomic():
        result, _ = ReferralContestResult.objects.update_or_create(
            contest=contest,
            defaults={
                'winners_json': winners,
                'leaderboard_snapshot_json': top_snapshot,
                'stats_json': stats,
                'payout_json': payout_json,
                'finalized_at': timezone.now(),
            },
        )
        ContestWinnerPayout.objects.filter(
            contest=contest, source=ContestWinnerPayout.SOURCE_REFERRAL
        ).delete()
        if payout_rows:
            ContestWinnerPayout.objects.bulk_create(payout_rows)
    invalidate_referral_leaderboard_cache(contest.id)

    # Notifications « mois clos » pour le podium referral (best-effort).
    for w in winners[: min(10, len(winners))]:
        uid = w.get('referrer_id')
        if not uid:
            continue
        u = User.objects.filter(pk=uid).first()
        if u:
            notify_referral_contest_month_closed(
                recipient=u,
                contest_key=contest.contest_key,
                rank=int(w.get('rank') or 0),
                score=float(w.get('score') or 0.0),
            )
    return result
