"""Recalcul du quality score (pénalités hides/reports, bonus engagement / watch)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg
from django.utils import timezone

from ads.models import Ad, AdClick, AdHide, AdImpression, AdQualityScore, AdReport, AdView


def ensure_quality_row(ad: Ad) -> AdQualityScore:
    row, _ = AdQualityScore.objects.get_or_create(ad=ad, defaults={'quality_0_100': 72})
    return row


def recompute_ad_quality(ad_id) -> None:
    ad = Ad.objects.get(pk=ad_id)
    row = ensure_quality_row(ad)
    since = timezone.now() - timedelta(days=14)
    imps = AdImpression.objects.filter(ad=ad, served_at__gte=since)
    imp_n = imps.count()
    valid_n = imps.filter(is_valid=True).count()
    hides = AdHide.objects.filter(ad=ad, created_at__gte=since).count()
    reps = AdReport.objects.filter(ad=ad, created_at__gte=since).count()
    views = AdView.objects.filter(ad=ad, started_at__gte=since)
    v_n = views.count()
    watch_avg = views.aggregate(a=Avg('duration_ms'))['a'] or 0
    completes = views.filter(completed=True).count()

    hide_rate = Decimal(hides) / Decimal(max(1, imp_n))
    report_rate = Decimal(reps) / Decimal(max(1, imp_n))
    clicks = AdClick.objects.filter(ad=ad, clicked_at__gte=since).count()
    ctr = Decimal(clicks) / Decimal(max(1, valid_n))

    penalty_h = hide_rate * Decimal('120')
    penalty_r = report_rate * Decimal('200')
    watch_bonus = min(Decimal('12'), Decimal(int(watch_avg or 0)) / Decimal('4000'))
    eng_bonus = min(Decimal('10'), Decimal(completes) / Decimal(max(1, v_n)) * Decimal('10'))

    base = Decimal('72') + watch_bonus + eng_bonus - penalty_h - penalty_r
    q = int(max(5, min(100, float(base))))
    row.quality_0_100 = q
    row.hide_rate = hide_rate
    row.report_rate = report_rate
    row.ctr_smoothed = ctr
    row.watch_bonus = watch_bonus
    row.engagement_bonus = eng_bonus
    row.penalty_hidden = penalty_h
    row.penalty_reported = penalty_r
    row.save()
