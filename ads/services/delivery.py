"""
Insertion native : pas de « 1 pub tous les X posts » ; scoring + diversification + caps.
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal
from typing import Any

from django.core.cache import caches
from django.utils import timezone

from ads import constants as ac
from ads.models import AdDeliveryLog, AdHide
from ads.services.ranking import final_ad_rank_score
from ads.services.targeting import build_user_context, eligible_ads_queryset, passes_hard_targeting

_PLACEMENT_FORMATS: dict[str, tuple[str, ...]] = {
    ac.PLACEMENT_FEED_MOBILE: (ac.AD_FORMAT_FEED_VIDEO, ac.AD_FORMAT_FEED_IMAGE),
    ac.PLACEMENT_FEED_WEB: (ac.AD_FORMAT_FEED_VIDEO, ac.AD_FORMAT_FEED_IMAGE),
    ac.PLACEMENT_SIDEBAR_WEB: (ac.AD_FORMAT_SIDEBAR_NATIVE, ac.AD_FORMAT_FEED_IMAGE),
    ac.PLACEMENT_EXPLORE: (ac.AD_FORMAT_EXPLORE_NATIVE, ac.AD_FORMAT_FEED_VIDEO, ac.AD_FORMAT_FEED_IMAGE),
}


def _cache():
    try:
        return caches['ads']
    except Exception:
        return caches['default']


def _user_opted_out(user) -> bool:
    if user and user.is_authenticated:
        profile = getattr(user, 'profile', None)
        if profile and not getattr(profile, 'ad_ads_enabled', True):
            return True
    return False


def _budget_allows(ad) -> bool:
    b = getattr(ad.campaign, 'budget', None)
    if not b:
        return True
    if b.budget_micro <= 0:
        return True
    if b.budget_type == ac.BUDGET_TYPE_DAILY:
        today = timezone.now().date()
        if b.day_cursor != today:
            return True
        return b.spend_micro_day < b.budget_micro
    return b.spend_micro < b.budget_micro


def _session_cap_ok(placement: str, session_depth: int) -> bool:
    """Probabilité croissante avec la profondeur : évite les pubs en haut de feed uniquement."""
    if session_depth <= 2:
        return random.random() < 0.18
    if session_depth <= 8:
        return random.random() < 0.32
    return random.random() < 0.45


def _mmr_diversify(ranked: list[tuple[Decimal, Any]], k: int, lambda_mult: Decimal = Decimal('0.7')) -> list:
    """Sélection MMR simplifiée sur ``campaign_id`` pour limiter la répétition d’un même annonceur."""
    chosen = []
    candidates = list(ranked)
    while candidates and len(chosen) < k:
        best_i = 0
        best_adj = Decimal('-1')
        for i, (score, ad) in enumerate(candidates):
            sim_pen = Decimal('0')
            for _, a2 in chosen:
                if a2.campaign_id == ad.campaign_id:
                    sim_pen += Decimal('0.25')
                if a2.creative_id == ad.creative_id:
                    sim_pen += Decimal('0.15')
            adj = score - lambda_mult * sim_pen
            if adj > best_adj:
                best_adj = adj
                best_i = i
        chosen.append(candidates.pop(best_i))
    return [ad for _, ad in chosen]


def select_native_ads(
    *,
    placement: str,
    user,
    client: dict[str, Any],
    limit: int = 2,
    session_depth: int = 0,
    request_id: uuid.UUID | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Retourne une liste d’annonces natives classées pour le placement demandé.
    """
    meta: dict[str, Any] = {'reason': 'ok', 'candidates': 0}
    if placement not in _PLACEMENT_FORMATS:
        meta['reason'] = 'unknown_placement'
        return [], meta
    if _user_opted_out(user):
        meta['reason'] = 'user_opt_out'
        return [], meta
    if not _session_cap_ok(placement, session_depth):
        meta['reason'] = 'session_soft_cap'
        return [], meta

    ctx = build_user_context(user, client)
    qs = eligible_ads_queryset().filter(ad_format__in=_PLACEMENT_FORMATS[placement])
    ads = list(qs[:800])
    meta['candidates'] = len(ads)

    hidden_ids = set()
    if ctx.user_id:
        hidden_ids = set(AdHide.objects.filter(user_id=ctx.user_id).values_list('ad_id', flat=True))

    scored: list[tuple[Decimal, Any]] = []
    for ad in ads:
        if ad.pk in hidden_ids:
            continue
        if not passes_hard_targeting(ad, ctx):
            continue
        if not _budget_allows(ad):
            continue
        s = final_ad_rank_score(ad, ctx, session_depth=session_depth)
        if s <= 0:
            continue
        scored.append((s, ad))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(30, limit * 15)]
    picked = _mmr_diversify(top, min(limit, len(top)))

    rid = request_id or uuid.uuid4()
    if picked:
        AdDeliveryLog.objects.create(
            request_id=rid,
            user_id=ctx.user_id,
            placement=placement,
            candidates=[str(a.pk) for a in picked],
            scores={'top': [float(s) for s, _ in top[:15]]},
            chosen_ad=picked[0],
            reason='mmr',
        )

    # Cache court pour cohérence multi-requêtes
    if ctx.user_id and picked:
        key = f'ads:last:{ctx.user_id}:{placement}'
        try:
            _cache().set(key, [str(a.pk) for a in picked], timeout=45)
        except Exception:
            pass

    return picked, meta
