"""
Anti-fraude publicitaire : clics suspects, ferme-ferme, patterns automatisés.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from ads.models import AdClick


def evaluate_click_suspicion(user, ad, metadata: dict | None) -> tuple[bool, list[str]]:
    """Retourne (is_suspicious, raisons). Heuristiques légères, extensibles."""
    reasons: list[str] = []
    if not user or not getattr(user, 'is_authenticated', False):
        return False, reasons

    window_start = timezone.now() - timedelta(seconds=30)
    burst = AdClick.objects.filter(user=user, clicked_at__gte=window_start).count()
    max_burst = int(getattr(settings, 'ADS_ANTIFRAUD_MAX_CLICKS_30S', 8))
    if burst >= max_burst:
        reasons.append('click_burst')

    if metadata:
        if metadata.get('synthetic', False):
            reasons.append('synthetic_flag')
        if metadata.get('time_to_click_ms') is not None:
            ttc = int(metadata['time_to_click_ms'])
            if ttc < 40:
                reasons.append('too_fast_click')

    return (len(reasons) > 0), reasons


def evaluate_impression_validity(user, metadata: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metadata and metadata.get('viewport_pct', 100) < 5:
        reasons.append('not_visible')
    return (len(reasons) == 0), reasons


def update_user_trust_from_click(user, suspicious: bool) -> None:
    from ads.models import UserTrustScore

    if not user or not user.is_authenticated:
        return
    row, _ = UserTrustScore.objects.get_or_create(user=user, defaults={'trust': Decimal('0.75')})
    if suspicious:
        row.trust = max(Decimal('0.05'), (row.trust or Decimal('0.75')) - Decimal('0.03'))
    else:
        row.trust = min(Decimal('1'), (row.trust or Decimal('0.75')) + Decimal('0.002'))
    row.save(update_fields=['trust', 'updated_at'])


def advertiser_spam_guard(advertiser_id) -> bool:
    """True si l’annonceur doit être ralenti (trop de signalements récents)."""
    from ads.models import Ad, AdReport

    since = timezone.now() - timedelta(days=7)
    cnt = AdReport.objects.filter(created_at__gte=since, ad__campaign__business_account__advertiser_id=advertiser_id).aggregate(
        c=Count('id')
    )['c']
    return (cnt or 0) > int(getattr(settings, 'ADS_ANTIFRAUD_MAX_REPORTS_7D', 200))
