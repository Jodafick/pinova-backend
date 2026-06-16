"""Fusion préférences onboarding (profile.interests) + signaux comportementaux existants."""
from __future__ import annotations

from django.db.models import Q

from fotos.models import Topic

from .reference_data import normalize_interest_slugs

PROFILE_INTEREST_TOPIC_WEIGHT = 3


def interest_slugs_for_user(user, query_slugs=None) -> list[str]:
    if query_slugs:
        return normalize_interest_slugs(query_slugs)
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return []
    profile = getattr(user, 'profile', None)
    if not profile:
        return []
    return normalize_interest_slugs(getattr(profile, 'interests', None))


def _topic_match_q_for_slug(slug: str) -> Q:
    slug = (slug or '').strip().lower()
    if not slug:
        return Q(pk__in=[])
    human = slug.replace('-', ' ').replace('_', ' ')
    return (
        Q(slug=slug)
        | Q(slug__icontains=slug)
        | Q(name__icontains=human)
        | Q(name__icontains=slug)
    )


def topic_ids_for_interest_slugs(slugs) -> list[int]:
    normalized = normalize_interest_slugs(slugs)
    if not normalized:
        return []
    topic_q = Q()
    for slug in normalized:
        topic_q |= _topic_match_q_for_slug(slug)
    return list(
        Topic.objects.filter(is_active=True)
        .filter(topic_q)
        .values_list('id', flat=True)
        .distinct()
    )


def topic_names_for_interest_slugs(slugs) -> list[str]:
    ids = topic_ids_for_interest_slugs(slugs)
    if not ids:
        return []
    return list(Topic.objects.filter(id__in=ids).values_list('name', flat=True))


def merge_profile_interests_into_topic_scores(scores: dict, user, *, extra_slugs=None, weight: int = PROFILE_INTEREST_TOPIC_WEIGHT) -> dict:
    slugs = interest_slugs_for_user(user, extra_slugs)
    for name in topic_names_for_interest_slugs(slugs):
        scores[name] = scores.get(name, 0) + weight
    return scores


def profile_interest_topic_ids(user) -> list[int]:
    return topic_ids_for_interest_slugs(interest_slugs_for_user(user))
