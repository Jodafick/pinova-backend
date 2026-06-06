"""Heuristique d'estimation de portée pour un boost pin."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from pins.models import PinViewEvent

# Multiplicateurs par durée de pack (heures) — ordre de grandeur, pas une garantie.
_DURATION_MULTIPLIERS: dict[int, float] = {
    24: 2.2,
    72: 3.8,
    168: 6.5,
}


def _baseline_views(pin, days: int = 7) -> int:
    since = timezone.now() - timedelta(days=days)
    return PinViewEvent.objects.filter(pin=pin, created_at__gte=since).count()


def estimate_boost_reach(pin, duration_hours: int) -> dict:
    """
    Retourne une fourchette estimée de vues additionnelles pendant le boost.
    Basé sur les vues récentes du pin + multiplicateur durée.
    """
    baseline = _baseline_views(pin)
    mult = _DURATION_MULTIPLIERS.get(int(duration_hours))
    if mult is None:
        mult = max(1.8, min(8.0, float(duration_hours) / 18.0))

    if baseline <= 0:
        floor = max(40, int(duration_hours * 2.5))
        ceiling = max(floor + 30, int(floor * 1.6))
    else:
        raw = baseline * mult
        floor = max(int(raw * 0.75), baseline + 15)
        ceiling = max(floor + 20, int(raw * 1.35))

    return {
        'baseline_views_7d': baseline,
        'estimated_min': floor,
        'estimated_max': ceiling,
        'duration_hours': int(duration_hours),
        'heuristic': True,
    }
