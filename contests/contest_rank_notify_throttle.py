"""
Anti-spam pour les notifications de classement concours (push + in-app).

Utilise le cache Django (Redis recommandé en prod). En dev sans cache explicite,
LocMemCache suffit pour tests unitaires manuels.
"""

from __future__ import annotations

import time

from django.core.cache import cache

# Fenêtre minimale entre deux notifications concours (même utilisateur, même mois).
STANDARD_COOLDOWN_SEC = 120
# Transitions « prioritaires » (podium, entrée/sortie top 10 affiché) : intervalle réduit mais non nul.
PRIORITY_COOLDOWN_SEC = 42
# Plafond horizontal pour éviter une rafale même avec oscillations légitimes.
MAX_NOTIFICATIONS_PER_HOUR = 12


def _is_priority_transition(prev_rank: int | None, new_rank: int | None) -> bool:
    """Prix ou rupture avec le top 10 « affiché » (aligné produit sur le leaderboard dédupliqué)."""
    p = prev_rank if prev_rank is not None else 9999
    n = new_rank if new_rank is not None else 9999
    if min(p, n) <= 3:
        return True
    in10_p = p <= 10
    in10_n = n <= 10
    return in10_p != in10_n


def allow_contest_rank_notification(*, recipient_id: int, contest_key: str, prev_rank: int | None, new_rank: int | None) -> bool:
    priority = _is_priority_transition(prev_rank, new_rank)
    cooldown = PRIORITY_COOLDOWN_SEC if priority else STANDARD_COOLDOWN_SEC
    ck_last = f'contest_rn:last:{recipient_id}:{contest_key}'
    ck_hour = f'contest_rn:hc:{recipient_id}:{contest_key}'
    now = time.time()
    last = cache.get(ck_last)
    if last is not None:
        try:
            if now - float(last) < cooldown:
                return False
        except (TypeError, ValueError):
            pass
    try:
        count = int(cache.get(ck_hour) or 0)
    except (TypeError, ValueError):
        count = 0
    if count >= MAX_NOTIFICATIONS_PER_HOUR:
        return False
    cache.set(ck_last, str(now), timeout=max(86400, cooldown * 4))
    cache.set(ck_hour, count + 1, timeout=3600)
    return True
