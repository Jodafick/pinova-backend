"""
Signaux pour recalcul des intérêts (brancher depuis pins : like, comment, watch, etc.).

Exemple d’utilisation (dans pins.signals)::

    from ads.signals import record_user_content_signal

    record_user_content_signal(user, 'like', topic_slugs=['mode'], hashtag_names=['summer'])
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from ads import constants as ac
from ads.models import UserInterestScore

User = get_user_model()

_SIGNAL_WEIGHTS = {
    'like': 1.0,
    'comment': 1.4,
    'share': 1.6,
    'follow': 2.0,
    'watch_sec': 0.02,
    'search': 1.1,
    'category_view': 0.35,
}


def record_user_content_signal(
    user,
    signal_type: str,
    *,
    topic_slugs: Optional[Iterable[str]] = None,
    hashtag_names: Optional[Iterable[str]] = None,
    category_slugs: Optional[Iterable[str]] = None,
    search_query: Optional[str] = None,
) -> None:
    """Mise à jour incrémentale des ``UserInterestScore`` (appel synchrone léger)."""
    if not user or not user.is_authenticated:
        return
    weight = _SIGNAL_WEIGHTS.get(signal_type, 0.5)
    now = timezone.now()

    def bump(key_type: str, key_slug: str, delta: float):
        if not key_slug:
            return
        slug = str(key_slug).strip().lower()[:190]
        if not slug:
            return
        row, _ = UserInterestScore.objects.get_or_create(
            user=user,
            key_type=key_type,
            key_slug=slug,
            defaults={'raw_score': 0, 'score': 0},
        )
        from decimal import Decimal

        d = Decimal(str(delta))
        row.raw_score = (row.raw_score or 0) + d
        row.score = row.raw_score
        row.last_signal_at = now
        counts = row.source_counts or {}
        counts[signal_type] = float(counts.get(signal_type, 0)) + float(delta)
        row.source_counts = counts
        row.save(update_fields=['raw_score', 'score', 'last_signal_at', 'source_counts', 'updated_at'])

    for t in topic_slugs or []:
        bump(ac.INTEREST_KEY_TOPIC, t, weight)
    for h in hashtag_names or []:
        bump(ac.INTEREST_KEY_HASHTAG, h.lstrip('#'), weight)
    for c in category_slugs or []:
        bump(ac.INTEREST_KEY_CATEGORY, c, weight * 0.8)
    if search_query:
        bump(ac.INTEREST_KEY_SEARCH, search_query.strip()[:120], weight)
    # watch_seconds : agrégé dans ``UserBehaviorProfile`` via tâches périodiques / batch events.
