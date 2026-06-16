from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from django.db.models import F
from django.utils import timezone

from accounts.models import Profile

from .models import PartnerCampaign, FotoBoost, FotoPromoCampaign
from .targeting import user_matches_targeting

FEED_PARTNER_AD_EVERY_N = 8


def effective_ad_policy(profile: Profile | None) -> dict[str, bool]:
    """Pubs réseau (AdSense/AdMob) et partenaire selon l’abonnement."""
    if profile is None or profile.subscription_plan == Profile.PLAN_FREE:
        return {'network': True, 'partner': True}
    if profile.subscription_plan == Profile.PLAN_PLUS:
        return {'network': False, 'partner': True}
    if profile.subscription_plan == Profile.PLAN_PRO:
        return {'network': False, 'partner': False}
    return {'network': True, 'partner': True}


def _profile_for_user(user):
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return None
    try:
        return user.profile
    except Exception:
        return None


def _campaign_matches_user(campaign: PartnerCampaign, user, topic: str) -> bool:
    if not campaign.is_live():
        return False
    return user_matches_targeting(
        user,
        _profile_for_user(user),
        topic_context=topic,
        spec=getattr(campaign, 'targeting', None),
        legacy_topic_slug=campaign.topic_slug,
        legacy_country_code=campaign.country_code,
    )


def _foto_promo_matches_user(campaign: FotoPromoCampaign, user, topic: str) -> bool:
    if not campaign.is_live():
        return False
    if campaign.owner_id == getattr(user, 'id', None):
        return False
    return user_matches_targeting(
        user,
        _profile_for_user(user),
        topic_context=topic,
        spec=getattr(campaign, 'targeting', None),
        legacy_topic_slug=campaign.topic_slug,
        legacy_country_code='',
    )


def pick_partner_campaigns(user, topic: str = '', limit: int = 2) -> list[PartnerCampaign]:
    profile = user.profile if user and user.is_authenticated else None
    if not effective_ad_policy(profile)['partner']:
        return []
    now = timezone.now()
    from django.db.models import Q

    qs = (
        PartnerCampaign.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )
    candidates = [c for c in qs[:80] if _campaign_matches_user(c, user, topic)]
    if not candidates:
        return []
    random.shuffle(candidates)
    return candidates[:limit]


def _foto_image_url(pin, request) -> str:
    if not foto.image:
        return ''
    return request.build_absolute_uri(pin.image.url)


def pick_foto_promo_campaigns(user, topic: str = '', limit: int = 2) -> list[FotoPromoCampaign]:
    profile = user.profile if user and user.is_authenticated else None
    if not effective_ad_policy(profile)['partner']:
        return []
    now = timezone.now()
    from django.db.models import Q

    qs = (
        FotoPromoCampaign.objects.filter(status=FotoPromoCampaign.STATUS_ACTIVE)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .select_related('foto', 'owner', 'foto__author')
    )
    candidates: list[FotoPromoCampaign] = []
    for row in qs[:120]:
        if _foto_promo_matches_user(row, user, topic):
            candidates.append(row)
    if not candidates:
        return []
    random.shuffle(candidates)
    return candidates[:limit]


def _campaign_media(campaign: FotoPromoCampaign, request) -> tuple[str, str]:
    media_type = getattr(campaign, 'media_type', None) or FotoPromoCampaign.MEDIA_IMAGE
    if campaign.media and request:
        return request.build_absolute_uri(campaign.media.url), media_type
    if campaign.image and request:
        return request.build_absolute_uri(campaign.image.url), FotoPromoCampaign.MEDIA_IMAGE
    if campaign.foto_id:
        return _foto_image_url(campaign.foto, request), FotoPromoCampaign.MEDIA_IMAGE
    return '', FotoPromoCampaign.MEDIA_IMAGE


def serialize_foto_promo_campaign(campaign: FotoPromoCampaign, request) -> dict[str, Any]:
    owner_username = campaign.owner.username if campaign.owner_id else ''
    if campaign.foto_id:
        foto = campaign.foto
        title = (campaign.headline or foto.title or '').strip()
        body = (campaign.body or (pin.description or '')[:400]).strip()
        username = foto.author.username if foto.author_id else owner_username
        cta_url = (campaign.cta_url or '').strip()
        cta_label = (campaign.cta_label or '').strip() or ('Voir le foto' if not cta_url else 'En savoir plus')
        media_url, media_type = _campaign_media(campaign, request)
        return {
            'feed_type': 'foto_promo',
            'id': f'foto-promo-{campaign.id}',
            'campaign_id': campaign.id,
            'foto_slug': foto.slug,
            'foto_id': foto.id,
            'title': title,
            'body': body,
            'sponsor_name': f'@{username}' if username else '',
            'username': username,
            'image_url': media_url,
            'media_url': media_url,
            'media_type': media_type,
            'cta_label': cta_label,
            'cta_url': cta_url,
            'topic': getattr(pin, 'topic', '') or campaign.topic_slug or '',
        }
    title = (campaign.headline or '').strip()
    body = (campaign.body or '').strip()
    cta_url = (campaign.cta_url or '').strip()
    cta_label = (campaign.cta_label or '').strip() or 'En savoir plus'
    media_url, media_type = _campaign_media(campaign, request)
    return {
        'feed_type': 'foto_promo',
        'id': f'foto-promo-{campaign.id}',
        'campaign_id': campaign.id,
        'foto_slug': '',
        'foto_id': 0,
        'title': title,
        'body': body,
        'sponsor_name': f'@{owner_username}' if owner_username else '',
        'username': owner_username,
        'image_url': media_url,
        'media_url': media_url,
        'media_type': media_type,
        'cta_label': cta_label,
        'cta_url': cta_url,
        'topic': campaign.topic_slug or '',
    }


def serialize_partner_campaign(campaign: PartnerCampaign, request) -> dict[str, Any]:
    image_url = ''
    if campaign.image:
        image_url = request.build_absolute_uri(campaign.image.url)
    return {
        'feed_type': 'partner_ad',
        'id': f'partner-ad-{campaign.id}',
        'campaign_id': campaign.id,
        'title': campaign.title,
        'body': campaign.body,
        'sponsor_name': campaign.sponsor_name,
        'image_url': image_url,
        'cta_label': campaign.cta_label,
        'cta_url': campaign.cta_url,
    }


def interleave_partner_ads(
    request,
    pin_rows: list[dict],
    *,
    topic: str = '',
    page_number: int = 1,
) -> list[dict]:
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    profile = user.profile if user else None
    if not effective_ad_policy(profile)['partner']:
        for row in pin_rows:
            row.setdefault('feed_type', 'pin')
        return pin_rows

    ads_needed = max(1, len(pin_rows) // FEED_PARTNER_AD_EVERY_N) if pin_rows else 0
    if ads_needed == 0:
        for row in pin_rows:
            row.setdefault('feed_type', 'pin')
        return pin_rows

    partners = pick_partner_campaigns(user, topic=topic, limit=ads_needed)
    promos = pick_foto_promo_campaigns(user, topic=topic, limit=ads_needed)
    ad_pool: list[tuple[str, Any]] = []
    for c in partners:
        ad_pool.append(('partner', c))
    for c in promos:
        ad_pool.append(('promo', c))
    if not ad_pool:
        for row in pin_rows:
            row.setdefault('feed_type', 'pin')
        return pin_rows
    random.shuffle(ad_pool)

    out: list[dict] = []
    ad_idx = 0
    for i, row in enumerate(pin_rows):
        row = dict(row)
        row['feed_type'] = 'pin'
        out.append(row)
        pos = i + 1 + (page_number - 1) * max(len(pin_rows), 1)
        if pos % FEED_PARTNER_AD_EVERY_N == 0 and ad_idx < len(ad_pool):
            kind, item = ad_pool[ad_idx]
            if kind == 'partner':
                out.append(serialize_partner_campaign(item, request))
                PartnerCampaign.objects.filter(pk=item.pk).update(impressions=F('impressions') + 1)
            else:
                out.append(serialize_foto_promo_campaign(item, request))
                FotoPromoCampaign.objects.filter(pk=item.pk).update(impressions=F('impressions') + 1)
            ad_idx += 1
    return out


def pick_contextual_ad(request, *, placement: str = 'pin_detail', topic: str = '') -> dict[str, Any] | None:
    """Une pub native pour détail foto ou story (alternance partenaire / promo foto)."""
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    profile = user.profile if user else None
    if not effective_ad_policy(profile)['partner']:
        return None
    partners = pick_partner_campaigns(user, topic=topic, limit=1)
    promos = pick_foto_promo_campaigns(user, topic=topic, limit=1)
    pool: list[tuple[str, Any]] = []
    if partners:
        pool.append(('partner', partners[0]))
    if promos:
        pool.append(('promo', promos[0]))
    if not pool:
        return None
    random.shuffle(pool)
    kind, item = pool[0]
    if kind == 'partner':
        row = serialize_partner_campaign(item, request)
        row['placement'] = placement
        PartnerCampaign.objects.filter(pk=item.pk).update(impressions=F('impressions') + 1)
        return row
    row = serialize_foto_promo_campaign(item, request)
    row['placement'] = placement
    FotoPromoCampaign.objects.filter(pk=item.pk).update(impressions=F('impressions') + 1)
    return row


def active_boosted_foto_ids() -> set[int]:
    now = timezone.now()
    return set(
        FotoBoost.objects.filter(
            status=FotoBoost.STATUS_ACTIVE,
            ends_at__gt=now,
        ).values_list('foto_id', flat=True)
    )


def apply_boost_to_foto_queryset(qs):
    """Priorise légèrement les fotos avec boost actif (discover / reco)."""
    boosted = active_boosted_foto_ids()
    if not boosted:
        return qs
    from django.db.models import Case, When, Value, IntegerField

    return qs.annotate(
        _boost_sort=Case(
            When(pk__in=boosted, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by('-_boost_sort', 'media_sensitive_blur', '-created_at')


def activate_foto_promo_campaign(campaign: FotoPromoCampaign) -> None:
    from notifications.campaign_notifications import notify_foto_promo_campaign_started

    campaign = FotoPromoCampaign.objects.select_related('foto', 'owner', 'package').get(pk=campaign.pk)
    now = timezone.now()
    duration = campaign.package.duration_hours
    campaign.status = FotoPromoCampaign.STATUS_ACTIVE
    campaign.starts_at = now
    campaign.ends_at = now + timedelta(hours=duration)
    campaign.save(update_fields=['status', 'starts_at', 'ends_at', 'updated_at'])
    notify_foto_promo_campaign_started(campaign)
    if campaign.foto_id:
        FotoPromoCampaign.objects.filter(
            foto=campaign.foto,
            status=FotoPromoCampaign.STATUS_ACTIVE,
        ).exclude(pk=campaign.pk).update(status=FotoPromoCampaign.STATUS_EXPIRED)
        boost = FotoBoost.objects.create(
            foto=campaign.foto,
            owner=campaign.owner,
            package=campaign.package,
            status=FotoBoost.STATUS_PENDING,
        )
        activate_foto_boost(boost, skip_owner_notify=True)


def activate_foto_boost(boost: FotoBoost, *, skip_owner_notify: bool = False) -> None:
    from notifications.campaign_notifications import notify_foto_boost_started

    boost = FotoBoost.objects.select_related('foto', 'owner', 'package').get(pk=boost.pk)
    now = timezone.now()
    duration = boost.package.duration_hours
    boost.status = FotoBoost.STATUS_ACTIVE
    boost.starts_at = now
    boost.ends_at = now + timedelta(hours=duration)
    boost.save(update_fields=['status', 'starts_at', 'ends_at', 'updated_at'])
    FotoBoost.objects.filter(
        foto=boost.foto,
        status=FotoBoost.STATUS_ACTIVE,
    ).exclude(pk=boost.pk).update(status=FotoBoost.STATUS_EXPIRED)
    if not skip_owner_notify:
        notify_foto_boost_started(boost)


def network_ad_config_payload(request) -> dict[str, Any]:
    """Config pubs réseau (AdSense / AdMob) selon plan et préférences utilisateur."""
    from django.conf import settings

    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    profile = _profile_for_user(user)
    policy_on = effective_ad_policy(profile)['network']

    web_configured = bool(
        settings.ADSENSE_CLIENT_ID
        and (settings.ADSENSE_SLOT_FEED or settings.ADSENSE_SLOT_DETAIL)
    )
    mobile_configured = bool(
        (settings.ADMOB_APP_ID_ANDROID and settings.ADMOB_UNIT_FEED_ANDROID)
        or (settings.ADMOB_APP_ID_IOS and settings.ADMOB_UNIT_FEED_IOS)
    )

    web: dict[str, str] | None = None
    if web_configured:
        web = {
            'client_id': settings.ADSENSE_CLIENT_ID,
            'feed_slot': settings.ADSENSE_SLOT_FEED or settings.ADSENSE_SLOT_DETAIL,
            'detail_slot': settings.ADSENSE_SLOT_DETAIL or settings.ADSENSE_SLOT_FEED,
        }

    mobile: dict[str, str] | None = None
    if mobile_configured:
        mobile = {
            'app_id_android': settings.ADMOB_APP_ID_ANDROID,
            'app_id_ios': settings.ADMOB_APP_ID_IOS,
            'feed_unit_android': settings.ADMOB_UNIT_FEED_ANDROID,
            'feed_unit_ios': settings.ADMOB_UNIT_FEED_IOS,
            'detail_unit_android': settings.ADMOB_UNIT_DETAIL_ANDROID or settings.ADMOB_UNIT_FEED_ANDROID,
            'detail_unit_ios': settings.ADMOB_UNIT_DETAIL_IOS or settings.ADMOB_UNIT_FEED_IOS,
        }

    configured = web_configured or mobile_configured
    return {
        'enabled': policy_on,
        'configured': configured,
        'show': policy_on and configured,
        'feed_every_n': settings.NETWORK_AD_FEED_EVERY_N,
        'web': web,
        'mobile': mobile,
    }
