"""Expiration d’abonnement (annulation à l’échéance, changement de plan programmé).

Utilisé par les vues (à chaque requête sensible) et par la commande planifiée
`enforce_subscriptions_due` pour appliquer l’état sans attendre une requête utilisateur.
"""

from __future__ import annotations

from django.utils import timezone

from .models import Profile


def _enforce_subscription_state(profile: Profile) -> bool:
    """
    Si `subscription_renewal_at` est dépassée : applique `subscription_scheduled_plan`
    ou repasse en Free si annulation à l’échéance.

    Returns:
        True si le profil a été modifié et enregistré, False sinon.
    """
    now = timezone.now()
    if not profile.subscription_renewal_at or profile.subscription_renewal_at > now:
        return False
    if profile.subscription_scheduled_plan:
        profile.subscription_plan = profile.subscription_scheduled_plan
    elif profile.subscription_cancel_at_period_end:
        profile.subscription_plan = Profile.PLAN_FREE
    else:
        return False
    profile.subscription_scheduled_plan = ''
    profile.subscription_cancel_at_period_end = False
    profile.subscription_renewal_at = (
        None if profile.subscription_plan == Profile.PLAN_FREE else profile.subscription_renewal_at
    )
    if profile.subscription_plan == Profile.PLAN_FREE:
        profile.translation_quota_monthly = 5
        profile.translation_used_monthly = 0
        profile.ad_ads_enabled = True
        profile.partner_ads_enabled = True
        profile.tips_enabled = False
        profile.tips_url = ''
        from .subscription_seats import SUBSCRIPTION_BUNDLE_SOLO, revoke_all_seats_for_owner

        revoke_all_seats_for_owner(profile.user)
        profile.subscription_seat_bundle = SUBSCRIPTION_BUNDLE_SOLO
    profile.save(
        update_fields=[
            'subscription_plan',
            'subscription_scheduled_plan',
            'subscription_cancel_at_period_end',
            'subscription_renewal_at',
            'translation_quota_monthly',
            'translation_used_monthly',
            'ad_ads_enabled',
            'partner_ads_enabled',
            'tips_enabled',
            'tips_url',
            'subscription_seat_bundle',
        ]
    )
    return True
