"""
Règles anti-fraude referral : réutilise les seuils de confiance du concours actif quand disponible.
"""
from __future__ import annotations

from django.contrib.auth.models import User


def is_self_referral(*, referee_id: int, referrer_id: int) -> bool:
    return referee_id == referrer_id


def trust_for_new_device(actor_user_id: int | None) -> float:
    """Placeholder aligné sur contests/services._validate_interaction (trust par acteur)."""
    return 1.0 if actor_user_id else 0.5


def should_reject_low_trust(*, trust: float, threshold: float) -> bool:
    return trust < threshold
