"""Politique d'âge — COPPA/RGPD mineurs (inscription, publication)."""
from __future__ import annotations

from datetime import date

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

MIN_REGISTRATION_AGE = 13
ADULT_AGE = 18


def age_from_birth_date(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def validate_birth_date_allowed(birth_date: date | None) -> date | None:
    """Rejette les dates correspondant à un âge < 13 ans."""
    if birth_date is None:
        return None
    age = age_from_birth_date(birth_date)
    if age is not None and age < MIN_REGISTRATION_AGE:
        raise serializers.ValidationError(
            _('L’inscription est réservée aux personnes de %(min_age)s ans et plus.')
            % {'min_age': MIN_REGISTRATION_AGE},
        )
    if birth_date > date.today():
        raise serializers.ValidationError(_('La date de naissance ne peut pas être dans le futur.'))
    return birth_date


def profile_is_minor_teen(profile) -> bool:
    """13–17 ans inclus — restrictions publication."""
    if profile is None:
        return False
    age = age_from_birth_date(getattr(profile, 'birth_date', None))
    if age is None:
        return False
    return MIN_REGISTRATION_AGE <= age < ADULT_AGE


def profile_can_publish_content(profile) -> bool:
    """Les comptes 13–17 ans ne peuvent pas publier de contenu."""
    return not profile_is_minor_teen(profile)


def profile_minor_restricted_label(profile) -> str | None:
    if profile_is_minor_teen(profile):
        return 'teen_13_17'
    age = age_from_birth_date(getattr(profile, 'birth_date', None)) if profile else None
    if age is not None and age < MIN_REGISTRATION_AGE:
        return 'under_13'
    return None
