"""Traitement batch des événements publicitaires (queue ``AdPendingEvent``)."""

from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ads import constants as ac
from ads.models import (
    AdClick,
    AdImpression,
    AdPendingEvent,
    AdView,
    AdWatchSession,
)


def _parse_dt(value):
    if value is None:
        return timezone.now()
    if hasattr(value, 'year'):
        return value
    if isinstance(value, str):
        return parse_datetime(value) or timezone.now()
    return timezone.now()


def _imp_from_payload(p: dict) -> None:
    rid = p.get('request_id')
    try:
        request_uuid = uuid.UUID(str(rid)) if rid else uuid.uuid4()
    except (ValueError, TypeError):
        request_uuid = uuid.uuid4()
    AdImpression.objects.create(
        request_id=request_uuid,
        user_id=p.get('user_id'),
        ad_id=p['ad_id'],
        placement=p['placement'],
        is_valid=bool(p.get('is_valid', True)),
        client_context=p.get('client_context') or {},
        device_fingerprint_hash=p.get('device_fingerprint_hash') or '',
        ip_hash=p.get('ip_hash') or '',
        fraud_flags=p.get('fraud_flags') or [],
        metadata=p.get('metadata') or {},
    )
    # touch frequency
    if p.get('user_id'):
        from ads.models import AdFrequencyTracking

        row, _ = AdFrequencyTracking.objects.get_or_create(user_id=p['user_id'], ad_id=p['ad_id'])
        row.impressions_1h = min(32000, (row.impressions_1h or 0) + 1)
        row.impressions_24h = min(10_000_000, (row.impressions_24h or 0) + 1)
        row.impressions_7d = min(50_000_000, (row.impressions_7d or 0) + 1)
        row.last_shown_at = timezone.now()
        row.save()


def _click_from_payload(p: dict) -> None:
    AdClick.objects.create(
        impression_id=p.get('impression_id'),
        user_id=p.get('user_id'),
        ad_id=p['ad_id'],
        is_suspicious=bool(p.get('is_suspicious', False)),
        suspicion_reasons=p.get('suspicion_reasons') or [],
        metadata=p.get('metadata') or {},
    )


def _view_from_payload(p: dict) -> None:
    AdView.objects.create(
        impression_id=p.get('impression_id'),
        user_id=p.get('user_id'),
        ad_id=p['ad_id'],
        started_at=_parse_dt(p.get('started_at')),
        duration_ms=int(p.get('duration_ms') or 0),
        visible_pct_max=int(p.get('visible_pct_max') or 0),
        completed=bool(p.get('completed', False)),
        metadata=p.get('metadata') or {},
    )


def _watch_from_payload(p: dict) -> None:
    ended = p.get('ended_at')
    if ended is not None and not hasattr(ended, 'year'):
        ended = parse_datetime(ended) if isinstance(ended, str) else None
    AdWatchSession.objects.create(
        ad_view_id=p.get('ad_view_id'),
        user_id=p.get('user_id'),
        ad_id=p['ad_id'],
        started_at=_parse_dt(p.get('started_at')),
        ended_at=ended,
        total_watched_ms=int(p.get('total_watched_ms') or 0),
        milestones=p.get('milestones') or {},
        heartbeat_count=int(p.get('heartbeat_count') or 0),
        metadata=p.get('metadata') or {},
    )


_HANDLERS = {
    ac.PENDING_EVENT_IMPRESSION: _imp_from_payload,
    ac.PENDING_EVENT_CLICK: _click_from_payload,
    ac.PENDING_EVENT_VIEW: _view_from_payload,
    ac.PENDING_EVENT_WATCH: _watch_from_payload,
}


def flush_pending_events(limit: int = 500) -> int:
    """Marque les événements traités ; retourne le nombre appliqués."""
    qs = AdPendingEvent.objects.filter(processed_at__isnull=True).order_by('id')[:limit]
    n = 0
    for ev in qs:
        with transaction.atomic():
            ev = AdPendingEvent.objects.select_for_update().filter(pk=ev.pk, processed_at__isnull=True).first()
            if not ev:
                continue
            fn = _HANDLERS.get(ev.event_type)
            if fn:
                fn(ev.payload or {})
            ev.processed_at = timezone.now()
            ev.attempts = (ev.attempts or 0) + 1
            ev.save(update_fields=['processed_at', 'attempts'])
            n += 1
    return n
