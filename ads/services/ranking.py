"""
Formule de ranking publicitaire : sous-scores + enchère + fraîcheur − fatigue.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import exp, log1p

from django.conf import settings
from django.utils import timezone

from ads import constants as ac
from ads.models import Ad, AdFrequencyTracking, AdTargeting
from ads.services.targeting import (
    UserAdsContext,
    behavioral_score,
    geo_score,
    interest_score,
    relevance_score,
)


@dataclass
class RankComponents:
    interest: Decimal
    behavioral: Decimal
    relevance: Decimal
    geo: Decimal
    quality: Decimal


def _quality_norm(ad: Ad) -> Decimal:
    try:
        q = ad.quality.quality_0_100
    except Exception:
        q = 70
    return Decimal(q) / Decimal('100')


def compute_rank_components(ad: Ad, ctx: UserAdsContext) -> RankComponents:
    try:
        t = ad.targeting
    except AdTargeting.DoesNotExist:
        t = None
    if t is None:
        return RankComponents(
            interest=Decimal('0.5'),
            behavioral=Decimal('1'),
            relevance=Decimal('0.5'),
            geo=Decimal('1'),
            quality=_quality_norm(ad),
        )
    return RankComponents(
        interest=interest_score(t, ctx),
        behavioral=behavioral_score(t, ctx),
        relevance=relevance_score(t, ctx),
        geo=geo_score(t, ctx),
        quality=_quality_norm(ad),
    )


def fatigue_multiplier(user_id: int | None, ad_id, session_depth: int) -> Decimal:
    """Réduit les répétitions : historique court + profondeur de session (pas « 1 pub / X posts »)."""
    if not user_id:
        return Decimal('1')
    try:
        row = AdFrequencyTracking.objects.get(user_id=user_id, ad_id=ad_id)
    except AdFrequencyTracking.DoesNotExist:
        return Decimal('1')
    imp24 = row.impressions_24h or 0
    imp7 = row.impressions_7d or 0
    # Soft cap : décroissance exponentielle légère
    f = exp(-0.12 * imp24) * exp(-0.02 * imp7)
    # Plus on scrolle profondément, plus on peut diversifier (léger bonus)
    diversify = 1.0 + 0.04 * log1p(max(0, session_depth))
    return Decimal(str(min(1.0, f * diversify)))


def final_ad_rank_score(
    ad: Ad,
    ctx: UserAdsContext,
    *,
    session_depth: int = 0,
) -> Decimal:
    w = getattr(settings, 'ADS_RANK_WEIGHTS', None) or {}
    w_bid = Decimal(str(w.get('bid', ac.DEFAULT_RANK_WEIGHT_BID)))
    w_rel = Decimal(str(w.get('relevance', ac.DEFAULT_RANK_WEIGHT_RELEVANCE)))
    w_qual = Decimal(str(w.get('quality', ac.DEFAULT_RANK_WEIGHT_QUALITY)))
    w_fresh = Decimal(str(w.get('freshness', ac.DEFAULT_RANK_WEIGHT_FRESHNESS)))
    w_eng = Decimal(str(w.get('engagement_pred', ac.DEFAULT_RANK_WEIGHT_ENGAGEMENT_PRED)))
    w_fatigue = Decimal(str(w.get('fatigue_penalty', ac.DEFAULT_RANK_FATIGUE_PENALTY)))

    comp = compute_rank_components(ad, ctx)
    blended_relevance = (
        comp.interest * Decimal('0.35')
        + comp.behavioral * Decimal('0.2')
        + comp.relevance * Decimal('0.3')
        + comp.geo * Decimal('0.15')
    )
    bid = Decimal(ad.campaign.bid_micro or 0) / Decimal('1000000')
    bid_norm = Decimal(str(log1p(float(bid) + 1.0) / 5.0))  # ~ [0,1]

    age_hours = max(
        0.0,
        (timezone.now() - ad.created_at).total_seconds() / 3600.0,
    )
    freshness = Decimal(str(exp(-age_hours / 200.0)))  # lente décroissance

    engagement_pred = comp.relevance * Decimal('0.6') + comp.interest * Decimal('0.4')

    fatigue = fatigue_multiplier(
        user_id=ctx.user_id,
        ad_id=ad.pk,
        session_depth=session_depth,
    )
    trust = ctx.trust if ctx.trust is not None else Decimal('0.75')

    score = (
        w_bid * bid_norm
        + w_rel * blended_relevance
        + w_qual * comp.quality
        + w_fresh * freshness
        + w_eng * engagement_pred
        - w_fatigue * (Decimal('1') - fatigue)
    ) * trust

    boost = Decimal(ad.priority_boost or 0) / Decimal('100')
    return max(Decimal('0'), score + boost)


