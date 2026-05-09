"""Tâches Celery : decay intérêts, agrégats analytics, flush queue, quality score."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.db.models import Sum
from django.utils import timezone

from ads import constants as ac
from ads.models import Ad, AdClick, AdHide, AdImpression, AdPerformanceSnapshot, AdReport, AdView, UserInterestScore
from ads.services.event_pipeline import flush_pending_events
from ads.services.quality import recompute_ad_quality


@shared_task(name='ads.flush_pending_events')
def task_flush_pending_events(limit: int = 500) -> int:
    return flush_pending_events(limit=limit)


@shared_task(name='ads.decay_interest_scores')
def task_decay_interest_scores(batch_size: int = 2000) -> int:
    """Decay temporel sur les scores peu récents."""
    cutoff = timezone.now() - timedelta(days=10)
    qs = UserInterestScore.objects.filter(last_signal_at__lt=cutoff)[:batch_size]
    n = 0
    for row in qs.iterator():
        row.score = (row.score or Decimal('0')) * Decimal('0.985')
        row.raw_score = (row.raw_score or Decimal('0')) * Decimal('0.985')
        row.save(update_fields=['score', 'raw_score', 'updated_at'])
        n += 1
    return n


@shared_task(name='ads.recompute_quality_all')
def task_recompute_quality_all() -> int:
    ids = list(Ad.objects.filter(status=ac.AD_STATUS_ACTIVE).values_list('id', flat=True)[:500])
    for pk in ids:
        recompute_ad_quality(pk)
    return len(ids)


@shared_task(name='ads.recompute_quality_one')
def task_recompute_quality_one(ad_id: str) -> None:
    recompute_ad_quality(ad_id)


@shared_task(name='ads.rollup_hourly_snapshots')
def task_rollup_hourly_snapshots() -> int:
    """Crée des snapshots horaires pour la dernière heure close."""
    end = timezone.now().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    created = 0
    for ad in Ad.objects.filter(status=ac.AD_STATUS_ACTIVE).iterator():
        imps = AdImpression.objects.filter(ad=ad, served_at__gte=start, served_at__lt=end)
        imp_n = imps.count()
        if imp_n == 0:
            continue
        valid_n = imps.filter(is_valid=True).count()
        clicks = AdClick.objects.filter(ad=ad, clicked_at__gte=start, clicked_at__lt=end).count()
        views = AdView.objects.filter(ad=ad, started_at__gte=start, started_at__lt=end)
        v_n = views.count()
        completes = views.filter(completed=True).count()
        watch_sum = views.aggregate(s=Sum('duration_ms'))['s'] or 0
        watch_avg = int((watch_sum / v_n) if v_n else 0)
        hides = AdHide.objects.filter(ad=ad, created_at__gte=start, created_at__lt=end).count()
        reps = AdReport.objects.filter(ad=ad, created_at__gte=start, created_at__lt=end).count()
        ctr = Decimal(clicks) / Decimal(max(1, valid_n))
        eng = Decimal(completes) / Decimal(max(1, v_n))

        AdPerformanceSnapshot.objects.update_or_create(
            ad=ad,
            period_start=start,
            granularity=AdPerformanceSnapshot.GRANULARITY_HOUR,
            defaults={
                'period_end': end,
                'impressions': imp_n,
                'valid_impressions': valid_n,
                'clicks': clicks,
                'views': v_n,
                'completes': completes,
                'spend_micro': 0,
                'watch_duration_ms_total': watch_sum,
                'watch_duration_ms_avg': watch_avg,
                'engagement_events': completes,
                'hidden_count': hides,
                'reported_count': reps,
                'ctr': ctr,
                'cpm_micro': 0,
                'cpc_micro': 0,
                'engagement_rate': eng,
                'retention_proxy': eng,
            },
        )
        created += 1
    return created
