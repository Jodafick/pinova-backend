"""Defaults intelligents digest / recommandations."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from fotos.weekly_stats import count_foto_view_events_between

from .models import Profile


def _interest_count(profile) -> int:
    raw = getattr(profile, 'interests', None) or []
    if not isinstance(raw, list):
        return 0
    return len([x for x in raw if str(x).strip()])


def should_enable_recommendations(profile) -> bool:
    """Opt-in intelligent : intérêts onboarding renseignés."""
    return _interest_count(profile) >= 2


def should_enable_digest(profile) -> bool:
    """Digest Pro seulement si l'auteur a eu des vues sur 7 jours."""
    if profile.subscription_plan != Profile.PLAN_PRO:
        return False
    now = timezone.now()
    since = now - timedelta(days=7)
    views = count_foto_view_events_between(profile.user, since, now)
    return views > 0


def apply_smart_notification_defaults(
    profile,
    *,
    interests_updated: bool = False,
    onboarding_completed: bool = False,
) -> bool:
    """
    Active intelligemment reco/digest sans désactiver un choix explicite utilisateur.
    """
    changed_fields: list[str] = []

    if interests_updated or onboarding_completed:
        if not profile.notifications_recommendations and should_enable_recommendations(profile):
            profile.notifications_recommendations = True
            changed_fields.append('notifications_recommendations')

    if profile.subscription_plan == Profile.PLAN_PRO:
        if not profile.notifications_digest_creator_weekly and should_enable_digest(profile):
            profile.notifications_digest_creator_weekly = True
            changed_fields.append('notifications_digest_creator_weekly')

    if changed_fields:
        profile.save(update_fields=changed_fields)
        return True
    return False
