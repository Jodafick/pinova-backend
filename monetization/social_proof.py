"""Social proof A/B sur les packs boost."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import FotoBoost


def social_proof_variant_for_user(user) -> str:
    if user and getattr(user, 'is_authenticated', False) and user.id:
        return 'b' if user.id % 2 else 'a'
    return 'a'


def total_boosts_activated(days: int = 7) -> int:
    """Nombre total de boosts activés sur la période (social proof checkout)."""
    since = timezone.now() - timedelta(days=days)
    return (
        FotoBoost.objects.filter(created_at__gte=since)
        .exclude(status='canceled')
        .count()
    )


def recent_boost_counts_by_package(days: int = 7) -> dict[str, int]:
    since = timezone.now() - timedelta(days=days)
    rows = (
        FotoBoost.objects.filter(created_at__gte=since)
        .exclude(status='canceled')
        .values('package__slug')
        .annotate(n=Count('id'))
    )
    return {r['package__slug']: int(r['n']) for r in rows if r.get('package__slug')}


def enrich_boost_packages(packages, user) -> list[dict]:
    variant = social_proof_variant_for_user(user)
    counts = recent_boost_counts_by_package()
    slugs = [p.slug for p in packages]
    top_slug = max(slugs, key=lambda s: counts.get(s, 0)) if slugs else None

    out: list[dict] = []
    for idx, pack in enumerate(packages):
        row = {
            'slug': pack.slug,
            'label': pack.label,
            'duration_hours': pack.duration_hours,
            'amount': pack.amount,
            'currency_iso': pack.currency_iso,
            'social_proof_variant': variant,
            'is_highlighted': False,
            'social_proof_label': '',
            'recent_purchases_7d': counts.get(pack.slug, 0),
        }
        if variant == 'a':
            if idx == 1:
                row['is_highlighted'] = True
                row['social_proof_label'] = 'popular'
        else:
            if top_slug and pack.slug == top_slug and counts.get(pack.slug, 0) > 0:
                row['is_highlighted'] = True
                row['social_proof_label'] = 'creator_choice'
            elif idx == 1:
                row['is_highlighted'] = True
                row['social_proof_label'] = 'creator_choice'
        out.append(row)
    return out
