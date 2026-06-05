"""Ciblage campagnes publicitaires — critères profil utilisateur + contexte fil."""
from __future__ import annotations

from datetime import date
from typing import Any

from accounts.models import Profile

TARGETING_KEYS = (
    'countries',
    'languages',
    'currencies',
    'plans',
    'genders',
    'cities',
    'interests',
    'hobbies',
    'topics',
    'age_min',
    'age_max',
)


def _norm_list(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    for v in values:
        s = str(v or '').strip()
        if s:
            out.append(s)
    return out


def normalize_targeting(raw: dict | None) -> dict[str, Any]:
    data = dict(raw or {})
    return {
        'countries': [c.upper() for c in _norm_list(data.get('countries'))],
        'languages': [x.lower() for x in _norm_list(data.get('languages'))],
        'currencies': [x.upper() for x in _norm_list(data.get('currencies'))],
        'plans': [x.lower() for x in _norm_list(data.get('plans'))],
        'genders': [x.lower() for x in _norm_list(data.get('genders'))],
        'cities': [x.lower() for x in _norm_list(data.get('cities'))],
        'interests': [x.lower() for x in _norm_list(data.get('interests'))],
        'hobbies': [x.lower() for x in _norm_list(data.get('hobbies'))],
        'topics': [x.lower() for x in _norm_list(data.get('topics'))],
        'age_min': data.get('age_min') if data.get('age_min') is not None else None,
        'age_max': data.get('age_max') if data.get('age_max') is not None else None,
    }


def merge_legacy_targeting(
    targeting: dict | None,
    *,
    topic_slug: str = '',
    country_code: str = '',
) -> dict[str, Any]:
    spec = normalize_targeting(targeting)
    if topic_slug and not spec['topics']:
        spec['topics'] = [topic_slug.strip().lower()]
    if country_code and not spec['countries']:
        spec['countries'] = [country_code.strip().upper()]
    return spec


def _user_age(profile: Profile | None) -> int | None:
    if not profile or not profile.birth_date:
        return None
    today = date.today()
    bd = profile.birth_date
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    return max(0, age)


def _json_lower_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(v).strip().lower() for v in values if str(v).strip()}


def user_matches_targeting(
    user,
    profile: Profile | None,
    *,
    topic_context: str = '',
    spec: dict | None,
    legacy_topic_slug: str = '',
    legacy_country_code: str = '',
) -> bool:
    targeting = merge_legacy_targeting(
        spec,
        topic_slug=legacy_topic_slug,
        country_code=legacy_country_code,
    )

    has_any = any(
        [
            targeting['countries'],
            targeting['languages'],
            targeting['currencies'],
            targeting['plans'],
            targeting['genders'],
            targeting['cities'],
            targeting['interests'],
            targeting['hobbies'],
            targeting['topics'],
            targeting['age_min'] is not None,
            targeting['age_max'] is not None,
        ]
    )
    if not has_any:
        return True

    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False

    if not profile:
        return False

    if targeting['countries']:
        cc = (profile.country_code or '').upper()
        if not cc or cc not in targeting['countries']:
            return False

    if targeting['languages']:
        lang = (profile.preferred_language or '').lower()
        if not lang or lang not in targeting['languages']:
            return False

    if targeting['currencies']:
        cur = (profile.preferred_currency or '').upper()
        if not cur or cur not in targeting['currencies']:
            return False

    if targeting['plans']:
        plan = (profile.subscription_plan or Profile.PLAN_FREE).lower()
        if plan not in targeting['plans']:
            return False

    if targeting['genders']:
        gender = (profile.gender or '').lower()
        if not gender or gender not in targeting['genders']:
            return False

    if targeting['cities']:
        city = (profile.city or '').strip().lower()
        if not city:
            return False
        if not any(c in city or city in c for c in targeting['cities']):
            return False

    user_interests = _json_lower_set(profile.interests)
    if targeting['interests']:
        wanted = set(targeting['interests'])
        if not user_interests.intersection(wanted):
            return False

    user_hobbies = _json_lower_set(profile.hobbies)
    if targeting['hobbies']:
        wanted = set(targeting['hobbies'])
        if not user_hobbies.intersection(wanted):
            return False

    if targeting['topics']:
        t_ctx = (topic_context or '').strip().lower()
        wanted = set(targeting['topics'])
        topic_ok = bool(t_ctx and t_ctx in wanted)
        if not topic_ok and user_interests:
            topic_ok = bool(user_interests.intersection(wanted))
        if not topic_ok:
            return False

    age = _user_age(profile)
    if targeting['age_min'] is not None:
        if age is None or age < int(targeting['age_min']):
            return False
    if targeting['age_max'] is not None:
        if age is None or age > int(targeting['age_max']):
            return False

    return True


def targeting_options_payload(topics: list[dict]) -> dict[str, Any]:
    return {
        'countries': [
            {'code': 'BJ', 'label': 'Bénin'},
            {'code': 'BF', 'label': 'Burkina Faso'},
            {'code': 'CI', 'label': "Côte d'Ivoire"},
            {'code': 'FR', 'label': 'France'},
            {'code': 'GH', 'label': 'Ghana'},
            {'code': 'GN', 'label': 'Guinée'},
            {'code': 'ML', 'label': 'Mali'},
            {'code': 'NE', 'label': 'Niger'},
            {'code': 'NG', 'label': 'Nigeria'},
            {'code': 'SN', 'label': 'Sénégal'},
            {'code': 'TG', 'label': 'Togo'},
        ],
        'languages': [
            {'code': 'fr', 'label': 'Français'},
            {'code': 'en', 'label': 'English'},
        ],
        'currencies': [
            {'code': 'XOF', 'label': 'Franc CFA (XOF)'},
            {'code': 'EUR', 'label': 'Euro (EUR)'},
            {'code': 'USD', 'label': 'Dollar (USD)'},
        ],
        'plans': [
            {'code': 'free', 'label': 'Free'},
            {'code': 'plus', 'label': 'Plus'},
            {'code': 'pro', 'label': 'Pro'},
        ],
        'genders': [
            {'code': 'woman', 'label': 'Femme'},
            {'code': 'man', 'label': 'Homme'},
            {'code': 'non_binary', 'label': 'Non-binaire'},
            {'code': 'other', 'label': 'Autre'},
        ],
        'topics': topics,
        'interest_suggestions': [
            'déco',
            'voyage',
            'photo',
            'mode',
            'cuisine',
            'design',
            'architecture',
            'sport',
            'musique',
            'tech',
        ],
        'hobby_suggestions': [
            'photographie',
            'randonnée',
            'lecture',
            'gaming',
            'jardinage',
            'couture',
            'yoga',
            'bricolage',
        ],
    }
