"""
Moteur de ciblage : filtres d’éligibilité + sous-scores (géo, intérêts, comportement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from ads.models import Ad, AdTargeting, UserBehaviorProfile, UserInterestScore


@dataclass
class UserAdsContext:
    user_id: Optional[int]
    age: Optional[int]
    gender: str
    country_code: str
    city_label: str
    language: str
    device: str
    os: str
    interest_by_slug: dict[str, Decimal]
    watch_sec_7d: int
    engagement_rate: Decimal
    last_active_at: Optional[Any]
    category_slugs_recent: set[str]
    search_queries_recent: set[str]
    trust: Decimal


def _age_from_birth_date(birth_date) -> Optional[int]:
    if not birth_date:
        return None
    today = timezone.now().date()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def build_user_context(user: Optional[User], client: dict[str, Any]) -> UserAdsContext:
    """Construit le contexte à partir du profil Pinova + signaux client (device, geo session)."""
    user_id: Optional[int] = None
    age = None
    gender = ''
    country = (client.get('country_code') or '').upper()[:2]
    city = (client.get('city_label') or '').strip()
    language = (client.get('language') or 'fr').lower()[:12]
    device = (client.get('device') or 'phone').lower()[:32]
    os_name = (client.get('os') or '').lower()[:32]
    trust = Decimal('0.75')

    interest_map: dict[str, Decimal] = {}
    watch_sec_7d = 0
    engagement_rate = Decimal('0')
    last_active = None
    cat_hist: set[str] = set()
    search_hist: set[str] = set()

    if user and user.is_authenticated:
        user_id = user.pk
        profile = getattr(user, 'profile', None)
        if profile:
            age = _age_from_birth_date(getattr(profile, 'birth_date', None))
            country = (getattr(profile, 'country_code', '') or country or '').upper()[:2]
            language = (getattr(profile, 'preferred_language', None) or language).lower()[:12]
        try:
            bp = user.ad_behavior_profile
            watch_sec_7d = bp.total_watch_seconds_7d
            engagement_rate = bp.engagement_rate_30d or Decimal('0')
            last_active = bp.last_active_at
            cat_hist = set((bp.category_histogram or {}).keys())
            search_hist = set((bp.search_histogram or {}).keys())
        except UserBehaviorProfile.DoesNotExist:
            pass
        try:
            trust = user.ad_trust_score.trust
        except Exception:
            trust = Decimal('0.75')

        scores = UserInterestScore.objects.filter(user=user).order_by('-score')[:400]
        interest_map = {f'{s.key_type}:{s.key_slug}': (s.score or Decimal('0')) for s in scores}

    return UserAdsContext(
        user_id=user_id,
        age=age,
        gender=gender,
        country_code=country,
        city_label=city,
        language=language,
        device=device,
        os=os_name,
        interest_by_slug=interest_map,
        watch_sec_7d=watch_sec_7d,
        engagement_rate=engagement_rate,
        last_active_at=last_active,
        category_slugs_recent=cat_hist,
        search_queries_recent=search_hist,
        trust=trust,
    )


def geo_score(targeting: AdTargeting, ctx: UserAdsContext) -> Decimal:
    countries = targeting.countries or []
    if countries and ctx.country_code and ctx.country_code not in [c.upper() for c in countries]:
        return Decimal('0')
    cities = targeting.cities or []
    if cities and ctx.city_label:
        labels = [str(c.get('label', '')).lower() for c in cities if isinstance(c, dict)]
        if labels and ctx.city_label.lower() not in labels:
            return Decimal('0.35')
    return Decimal('1')


def interest_score(targeting: AdTargeting, ctx: UserAdsContext) -> Decimal:
    topics = set((targeting.interest_topic_slugs or []))
    cats = set((targeting.interest_category_slugs or []))
    if not topics and not cats:
        return Decimal('0.6')
    score = Decimal('0')
    hits = 0
    for t in topics:
        key = f'topic:{str(t).lower()}'
        if key in ctx.interest_by_slug:
            score += ctx.interest_by_slug[key]
            hits += 1
    for c in cats:
        key = f'category:{str(c).lower()}'
        if key in ctx.interest_by_slug:
            score += ctx.interest_by_slug[key]
            hits += 1
        if str(c).lower() in ctx.category_slugs_recent:
            score += Decimal('0.5')
            hits += 1
    if hits == 0:
        return Decimal('0.25')
    return min(Decimal('1'), score / (Decimal(hits) * Decimal('5')) + Decimal('0.2'))


def behavioral_score(targeting: AdTargeting, ctx: UserAdsContext) -> Decimal:
    out = Decimal('1')
    min_watch = targeting.behavior_min_watch_7d_sec
    if min_watch is not None and ctx.watch_sec_7d < min_watch:
        out *= Decimal('0.4')
    min_er = targeting.behavior_min_engagement_rate
    if min_er is not None and ctx.engagement_rate < min_er:
        out *= Decimal('0.55')
    recency_h = targeting.recency_active_within_hours
    if recency_h is not None and ctx.last_active_at:
        delta = timezone.now() - ctx.last_active_at
        if delta > timedelta(hours=recency_h):
            out *= Decimal('0.5')
    return out


def relevance_score(targeting: AdTargeting, ctx: UserAdsContext) -> Decimal:
    """Overlap hashtags / recherches."""
    inc_tags = {str(x).lower().lstrip('#') for x in (targeting.include_hashtags or [])}
    if not inc_tags:
        base = Decimal('0.55')
    else:
        user_tags = {k.split(':', 1)[-1] for k in ctx.interest_by_slug if k.startswith('hashtag:')}
        overlap = len(inc_tags & user_tags)
        base = Decimal('0.35') + Decimal('0.15') * Decimal(min(4, overlap))

    for kw in targeting.search_keywords or []:
        k = str(kw).lower()
        if any(k in q for q in ctx.search_queries_recent):
            base += Decimal('0.15')
    return min(Decimal('1'), base)


def passes_hard_targeting(ad: Ad, ctx: UserAdsContext) -> bool:
    try:
        t = ad.targeting
    except AdTargeting.DoesNotExist:
        return True
    if t.age_min is not None and ctx.age is not None and ctx.age < t.age_min:
        return False
    if t.age_max is not None and ctx.age is not None and ctx.age > t.age_max:
        return False
    langs = [str(x).lower() for x in (t.languages or [])]
    if langs and ctx.language and ctx.language not in langs:
        return False
    devices = [str(x).lower() for x in (t.devices or [])]
    if devices and ctx.device and ctx.device not in devices:
        return False
    oss = [str(x).lower() for x in (t.operating_systems or [])]
    if oss and ctx.os and ctx.os not in oss:
        return False
    if geo_score(t, ctx) == 0:
        return False
    return True


def eligible_ads_queryset():
    """Annonces actives dans la fenêtre temporelle (pacing budget dans ``delivery``)."""
    now = timezone.now()
    from ads import constants as ac

    return (
        Ad.objects.filter(status=ac.AD_STATUS_ACTIVE, campaign__status=ac.CAMPAIGN_STATUS_ACTIVE)
        .filter(Q(campaign__start_at__isnull=True) | Q(campaign__start_at__lte=now))
        .filter(Q(campaign__end_at__isnull=True) | Q(campaign__end_at__gte=now))
        .select_related('campaign', 'campaign__budget', 'creative', 'targeting', 'quality')
    )