"""Catalogue boost / campagnes — filtrage API (tarifs gérés via admin Django)."""
from __future__ import annotations

from django.db.models import Q

from .models import BoostPackage

PACKAGE_KIND_BOOST = BoostPackage.KIND_BOOST
PACKAGE_KIND_CAMPAIGN = BoostPackage.KIND_CAMPAIGN
PACKAGE_KIND_BOTH = BoostPackage.KIND_BOTH


def normalize_package_kind(raw: str | None) -> str | None:
    value = (raw or '').strip().lower()
    if value in {PACKAGE_KIND_BOOST, PACKAGE_KIND_CAMPAIGN, PACKAGE_KIND_BOTH}:
        return value
    if value in {'boost', 'boosts', 'pin_boost'}:
        return PACKAGE_KIND_BOOST
    if value in {'campaign', 'campaigns', 'promo', 'ads', 'pub'}:
        return PACKAGE_KIND_CAMPAIGN
    return None


def package_kind_filter(kind: str | None) -> Q:
    """Filtre ORM : packs utilisables pour le flux demandé."""
    normalized = normalize_package_kind(kind)
    if normalized == PACKAGE_KIND_BOOST:
        return Q(package_kind__in=[PACKAGE_KIND_BOOST, PACKAGE_KIND_BOTH])
    if normalized == PACKAGE_KIND_CAMPAIGN:
        return Q(package_kind__in=[PACKAGE_KIND_CAMPAIGN, PACKAGE_KIND_BOTH])
    return Q()


def active_packages_for_kind(kind: str | None = None):
    qs = BoostPackage.objects.filter(is_active=True)
    kind_q = package_kind_filter(kind)
    if kind_q:
        qs = qs.filter(kind_q)
    return qs.order_by('duration_hours', 'slug')


def package_allows_kind(package: BoostPackage, kind: str) -> bool:
    normalized = normalize_package_kind(kind)
    if normalized == PACKAGE_KIND_BOOST:
        return package.allows_boost()
    if normalized == PACKAGE_KIND_CAMPAIGN:
        return package.allows_campaign()
    return True
