from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    ContestInteractionEvent,
    ContestSettings,
    CreatorContestScore,
    LeaderboardEvent,
    PinContestScore,
)


@dataclass
class InteractionValidation:
    is_valid: bool
    reason: str = ''
    trust_score: float = 1.0


def _month_bounds(dt: datetime, tz_name: str) -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(tz_name or 'UTC')
    local_dt = dt.astimezone(tz)
    start = local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return (
        start.astimezone(dt_timezone.utc),
        next_start.astimezone(dt_timezone.utc),
        local_dt.strftime('%Y-%m'),
    )


def get_active_contest_settings(now: datetime | None = None) -> ContestSettings | None:
    now = now or timezone.now()
    current = (
        ContestSettings.objects.filter(is_active=True, start_at__lte=now, end_at__gt=now)
        .order_by('-contest_key')
        .first()
    )
    if current:
        return current
    return create_monthly_contest_if_missing(now=now)


def create_monthly_contest_if_missing(now: datetime | None = None) -> ContestSettings:
    now = now or timezone.now()
    start_at, end_at, contest_key = _month_bounds(now, 'UTC')
    existing = ContestSettings.objects.filter(contest_key=contest_key).first()
    if existing:
        if existing.start_at != start_at or existing.end_at != end_at:
            existing.start_at = start_at
            existing.end_at = end_at
            existing.save(update_fields=['start_at', 'end_at', 'updated_at'])
        return existing

    ContestSettings.objects.filter(is_active=True).update(is_active=False)
    return ContestSettings.objects.create(
        contest_key=contest_key,
        is_active=True,
        timezone='UTC',
        start_at=start_at,
        end_at=end_at,
    )


def _validate_interaction(*, settings: ContestSettings, actor_id: int, interaction_type: str, dwell_seconds: int, comment_text: str) -> InteractionValidation:
    if interaction_type == ContestInteractionEvent.TYPE_VIEW and dwell_seconds < settings.min_view_duration_seconds:
        return InteractionValidation(is_valid=False, reason='view_too_short', trust_score=0.4)
    if interaction_type == ContestInteractionEvent.TYPE_COMMENT and len((comment_text or '').strip()) < settings.comment_min_length:
        return InteractionValidation(is_valid=False, reason='comment_too_short', trust_score=0.4)
    # Placeholder trust score; can be replaced by a dedicated fraud service.
    trust = 1.0 if actor_id else 0.5
    if trust < settings.trust_score_threshold:
        return InteractionValidation(is_valid=False, reason='trust_below_threshold', trust_score=trust)
    return InteractionValidation(is_valid=True, trust_score=trust)


def _base_weight(settings: ContestSettings, interaction_type: str) -> float:
    return {
        ContestInteractionEvent.TYPE_LIKE: settings.weight_likes,
        ContestInteractionEvent.TYPE_VIEW: settings.weight_views,
        ContestInteractionEvent.TYPE_SHARE: settings.weight_shares * settings.share_boost_factor,
        ContestInteractionEvent.TYPE_SAVE: settings.weight_saves,
        ContestInteractionEvent.TYPE_COMMENT: settings.weight_comments,
    }.get(interaction_type, 0.0)


def _decay_multiplier(settings: ContestSettings, pin_created_at: datetime, now: datetime) -> float:
    if not settings.recency_decay_enabled:
        return 1.0
    age_hours = max(0.0, (now - pin_created_at).total_seconds() / 3600.0)
    return math.exp(-settings.decay_rate * age_hours)


def _rank_for_pin(contest: ContestSettings, score: float) -> int:
    higher = PinContestScore.objects.filter(contest=contest, adjusted_score__gt=score).count()
    return higher + 1


def _rank_for_creator(contest: ContestSettings, score: float) -> int:
    higher = CreatorContestScore.objects.filter(contest=contest, adjusted_score__gt=score).count()
    return higher + 1


def _emit_leaderboard_event(*, contest: ContestSettings, event_type: str, entity_type: str, entity_id: int, payload: dict):
    row = LeaderboardEvent.objects.create(
        contest=contest,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    group_name = f'contest_{contest.contest_key.replace("-", "_")}'
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'contest.event',
            'payload': {
                'sequence': row.sequence,
                'event_type': row.event_type,
                'entity_type': row.entity_type,
                'entity_id': row.entity_id,
                'payload': row.payload,
                'created_at': row.created_at.isoformat(),
            },
        },
    )


def _maybe_send_rank_notifications(*, settings: ContestSettings, pin_score: PinContestScore):
    if pin_score.rank <= 0:
        return
    from notifications.notification_i18n import create_localized_notification

    recipient = pin_score.creator
    metadata = {'contest_key': settings.contest_key, 'pin_id': pin_score.pin_id, 'rank': pin_score.rank}
    if settings.notify_top_10 and pin_score.rank <= 10 and (pin_score.previous_rank > 10 or pin_score.previous_rank == 0):
        create_localized_notification(
            recipient=recipient,
            notification_type='system',
            message_fr=f"Ton pin vient d'entrer dans le top 10 mensuel (#{pin_score.rank}).",
            pin_id=pin_score.pin_id,
            pin_slug=pin_score.pin.slug,
            metadata=metadata,
        )
    elif settings.notify_top_100 and pin_score.rank <= 100 and (pin_score.previous_rank > 100 or pin_score.previous_rank == 0):
        create_localized_notification(
            recipient=recipient,
            notification_type='system',
            message_fr=f"Ton pin vient d'entrer dans le top 100 mensuel (#{pin_score.rank}).",
            pin_id=pin_score.pin_id,
            pin_slug=pin_score.pin.slug,
            metadata=metadata,
        )


def track_contest_interaction(
    *,
    pin,
    actor,
    interaction_type: str,
    dwell_seconds: int = 0,
    metadata: dict | None = None,
    comment_text: str = '',
) -> None:
    settings = get_active_contest_settings()
    if not settings:
        return
    if pin.created_at < settings.start_at or pin.created_at >= settings.end_at:
        return

    now = timezone.now()
    validation = _validate_interaction(
        settings=settings,
        actor_id=getattr(actor, 'id', 0),
        interaction_type=interaction_type,
        dwell_seconds=max(0, int(dwell_seconds or 0)),
        comment_text=comment_text,
    )
    base = _base_weight(settings, interaction_type)
    delta = 0.0
    if validation.is_valid and base > 0:
        delta = base * _decay_multiplier(settings, pin.created_at, now) * validation.trust_score * settings.virality_multiplier

    with transaction.atomic():
        event = ContestInteractionEvent.objects.create(
            contest=settings,
            pin=pin,
            actor=actor,
            interaction_type=interaction_type,
            dwell_seconds=max(0, int(dwell_seconds or 0)),
            trust_score=validation.trust_score,
            metadata=metadata or {},
            is_valid=validation.is_valid,
            invalid_reason=validation.reason,
            score_delta=delta,
        )
        if delta <= 0:
            _emit_leaderboard_event(
                contest=settings,
                event_type='interaction_ignored',
                entity_type='pin',
                entity_id=pin.id,
                payload={'event_id': event.id, 'reason': validation.reason},
            )
            return

        pin_score, _ = PinContestScore.objects.select_for_update().get_or_create(
            contest=settings,
            pin=pin,
            defaults={'creator': pin.author},
        )
        prev_rank = pin_score.rank
        pin_score.raw_score = float(pin_score.raw_score) + delta
        pin_score.adjusted_score = float(pin_score.adjusted_score) + delta
        pin_score.previous_rank = prev_rank or 0
        if interaction_type == ContestInteractionEvent.TYPE_LIKE:
            pin_score.total_likes = F('total_likes') + 1
        elif interaction_type == ContestInteractionEvent.TYPE_VIEW:
            pin_score.total_views = F('total_views') + 1
        elif interaction_type == ContestInteractionEvent.TYPE_SAVE:
            pin_score.total_saves = F('total_saves') + 1
        elif interaction_type == ContestInteractionEvent.TYPE_SHARE:
            pin_score.total_shares = F('total_shares') + 1
        elif interaction_type == ContestInteractionEvent.TYPE_COMMENT:
            pin_score.total_comments = F('total_comments') + 1
        pin_score.save()
        pin_score.refresh_from_db()
        pin_score.rank = _rank_for_pin(settings, pin_score.adjusted_score)
        pin_score.save(update_fields=['rank', 'updated_at'])

        creator_score, _ = CreatorContestScore.objects.select_for_update().get_or_create(
            contest=settings,
            creator=pin.author,
        )
        creator_score.previous_rank = creator_score.rank or 0
        creator_score.adjusted_score = float(creator_score.adjusted_score) + delta
        creator_score.save(update_fields=['adjusted_score', 'previous_rank', 'updated_at'])
        creator_score.rank = _rank_for_creator(settings, creator_score.adjusted_score)
        creator_score.save(update_fields=['rank', 'updated_at'])

        _emit_leaderboard_event(
            contest=settings,
            event_type='pin_rank_updated',
            entity_type='pin',
            entity_id=pin.id,
            payload={
                'pin_id': pin.id,
                'contest_key': settings.contest_key,
                'score': round(pin_score.adjusted_score, 4),
                'rank': pin_score.rank,
                'previous_rank': prev_rank,
                'delta_score': round(delta, 4),
            },
        )
        _emit_leaderboard_event(
            contest=settings,
            event_type='creator_rank_updated',
            entity_type='creator',
            entity_id=pin.author_id,
            payload={
                'creator_id': pin.author_id,
                'contest_key': settings.contest_key,
                'score': round(creator_score.adjusted_score, 4),
                'rank': creator_score.rank,
                'previous_rank': creator_score.previous_rank,
            },
        )
        _maybe_send_rank_notifications(settings=settings, pin_score=pin_score)


def finalize_contest(contest: ContestSettings) -> None:
    if contest.end_at > timezone.now():
        return
    top = list(PinContestScore.objects.filter(contest=contest).select_related('pin', 'creator').order_by('rank', '-adjusted_score')[: contest.max_winners])
    winners = [
        {'rank': idx + 1, 'pin_id': row.pin_id, 'creator_id': row.creator_id, 'score': row.adjusted_score}
        for idx, row in enumerate(top)
    ]
    from .models import ContestResult
    ContestResult.objects.update_or_create(
        contest=contest,
        defaults={'winners_json': winners, 'payout_json': []},
    )
