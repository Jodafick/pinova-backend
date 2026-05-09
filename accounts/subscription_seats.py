"""
Sièges famille / petite équipe : limites strictes, invitations, révocation.

Famille : 5 invités maximum (hors titulaire payeur).
Équipe : 15 invités maximum (hors titulaire payeur).
Titulaire = compte ayant souscrit avec seat_bundle=family ou team (pas sponsorisé).

Toute tentative d’élévation doit repasser par ces gardes serveur uniquement (pas UI).
"""

from __future__ import annotations

import hashlib
import os
import secrets

from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User

from .models import Profile, SubscriptionSeatMember, SubscriptionSeatInvitation

SUBSCRIPTION_FAMILY_MAX_INVITEES = max(1, min(50, int(os.environ.get('SUBSCRIPTION_FAMILY_MAX_INVITEES', '5'))))
SUBSCRIPTION_TEAM_MAX_INVITEES = max(1, min(50, int(os.environ.get('SUBSCRIPTION_TEAM_MAX_INVITEES', '15'))))
SUBSCRIPTION_SEAT_INVITE_EXPIRY_HOURS = max(1, min(336, int(os.environ.get('SUBSCRIPTION_SEAT_INVITE_EXPIRY_HOURS', '72'))))
SUBSCRIPTION_BUNDLE_SOLO = 'solo'
SUBSCRIPTION_BUNDLE_FAMILY = 'family'
SUBSCRIPTION_BUNDLE_TEAM = 'team'


def _normalized_seat_bundle(raw) -> str:
    """Aligné avec accounts.views sans import circulaire."""
    value = str(raw or '').strip().lower()
    if value == SUBSCRIPTION_BUNDLE_FAMILY:
        return SUBSCRIPTION_BUNDLE_FAMILY
    if value == SUBSCRIPTION_BUNDLE_TEAM:
        return SUBSCRIPTION_BUNDLE_TEAM
    return SUBSCRIPTION_BUNDLE_SOLO


def max_invitees_for_bundle(bundle: str) -> int:
    kind = _normalized_seat_bundle(bundle)
    if kind == SUBSCRIPTION_BUNDLE_FAMILY:
        return SUBSCRIPTION_FAMILY_MAX_INVITEES
    if kind == SUBSCRIPTION_BUNDLE_TEAM:
        return SUBSCRIPTION_TEAM_MAX_INVITEES
    return 0


def mark_expired_invitations_now():
    qs = SubscriptionSeatInvitation.objects.filter(
        status=SubscriptionSeatInvitation.STATUS_PENDING,
        expires_at__lt=timezone.now(),
    )
    return qs.update(status=SubscriptionSeatInvitation.STATUS_EXPIRED)


def count_active_members(owner_user: User) -> int:
    return SubscriptionSeatMember.objects.filter(owner=owner_user).count()


def count_pending_invitations(owner_user: User) -> int:
    mark_expired_invitations_now()
    return SubscriptionSeatInvitation.objects.filter(
        owner=owner_user,
        status=SubscriptionSeatInvitation.STATUS_PENDING,
        expires_at__gte=timezone.now(),
    ).count()


def slots_used(owner_user: User) -> int:
    return count_active_members(owner_user) + count_pending_invitations(owner_user)


def owner_eligible_as_seat_hub(profile: Profile) -> bool:
    if profile.subscription_sponsor_id:
        return False
    if profile.subscription_plan not in {Profile.PLAN_PLUS, Profile.PLAN_PRO}:
        return False
    return _normalized_seat_bundle(profile.subscription_seat_bundle) in (
        SUBSCRIPTION_BUNDLE_FAMILY,
        SUBSCRIPTION_BUNDLE_TEAM,
    )


def invitee_eligible(invitee_profile: Profile) -> bool:
    """Invité doit être gratuit, sans sponsor, sans paiement Plus/Pro résiduel après enforce."""
    if invitee_profile.subscription_sponsor_id:
        return False
    if invitee_profile.subscription_plan != Profile.PLAN_FREE:
        return False
    if invitee_profile.subscription_renewal_at and invitee_profile.subscription_renewal_at > timezone.now():
        return False
    return True


def _hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def generate_invite_plain_token_and_hash() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, _hash_token(plain)


def revoke_all_seats_for_owner(owner: User):
    """Supprime invitations actives et retire le statut siège aux membres (retour gratuit)."""
    with transaction.atomic():
        SubscriptionSeatInvitation.objects.filter(
            owner=owner,
            status=SubscriptionSeatInvitation.STATUS_PENDING,
        ).update(status=SubscriptionSeatInvitation.STATUS_REVOKED)
        members = list(
            SubscriptionSeatMember.objects.filter(owner=owner).select_related(
                'member', 'member__profile',
            ),
        )
        for row in members:
            strip_member_seat_entitlement(row.member)
        SubscriptionSeatMember.objects.filter(owner=owner).delete()


def strip_member_seat_entitlement(member_user: User):
    p = Profile.objects.select_for_update().get(user_id=member_user.id)
    if not p.subscription_sponsor_id:
        return
    p.subscription_sponsor = None
    p.subscription_plan = Profile.PLAN_FREE
    p.translation_quota_monthly = 5
    p.translation_used_monthly = 0
    p.subscription_renewal_at = None
    p.subscription_cancel_at_period_end = False
    p.subscription_scheduled_plan = ''
    p.tips_enabled = False
    p.tips_url = ''
    p.save(
        update_fields=[
            'subscription_sponsor',
            'subscription_plan',
            'translation_quota_monthly',
            'translation_used_monthly',
            'subscription_renewal_at',
            'subscription_cancel_at_period_end',
            'subscription_scheduled_plan',
            'tips_enabled',
            'tips_url',
        ],
    )


def sync_member_entitlements_from_owner(owner: User):
    """Recopie tier titulaire sur les sièges. Doit être appelé sous transaction.atomic()."""
    if not owner_eligible_as_seat_hub(owner.profile):
        return
    ow = Profile.objects.select_for_update().get(pk=owner.profile.pk)
    qs = SubscriptionSeatMember.objects.filter(owner=owner).select_related('member')
    for row in qs:
        mp = Profile.objects.select_for_update().filter(pk=row.member.profile.pk).first()
        if not mp:
            continue
        mp.subscription_sponsor_id = owner.id
        mp.subscription_plan = ow.subscription_plan
        mp.subscription_renewal_at = ow.subscription_renewal_at
        mp.translation_quota_monthly = ow.translation_quota_monthly
        mp.subscription_cancel_at_period_end = ow.subscription_cancel_at_period_end
        mp.subscription_scheduled_plan = ow.subscription_scheduled_plan
        mp.save(
            update_fields=[
                'subscription_sponsor',
                'subscription_plan',
                'subscription_renewal_at',
                'translation_quota_monthly',
                'subscription_cancel_at_period_end',
                'subscription_scheduled_plan',
            ],
        )


def grant_member_seat(owner: User, member: User):
    """
    Crée le lien siège après acceptation invitation.
    Doit être appelé dans transaction.atomic().
    Lance ValueError si invariant violé (appelant traduit en HTTP 409).
    """
    ow = Profile.objects.select_for_update().get(pk=owner.profile.pk)
    mp = Profile.objects.select_for_update().get(pk=member.profile.pk)
    if SubscriptionSeatMember.objects.filter(member=member).exclude(owner=owner).exists():
        raise ValueError('member_already_has_seat_hub')
    if not owner_eligible_as_seat_hub(ow):
        raise ValueError('owner_ineligible')
    if not invitee_eligible(mp):
        raise ValueError('invitee_ineligible')

    existed = SubscriptionSeatMember.objects.filter(owner=owner, member=member).exists()
    active = SubscriptionSeatMember.objects.filter(owner=owner).count()
    cap = max_invitees_for_bundle(ow.subscription_seat_bundle)
    if not existed and active >= cap:
        raise ValueError('hub_full')

    SubscriptionSeatMember.objects.get_or_create(owner=owner, member=member)
    mp.subscription_sponsor_id = owner.id
    mp.subscription_plan = ow.subscription_plan
    mp.subscription_renewal_at = ow.subscription_renewal_at
    mp.translation_quota_monthly = ow.translation_quota_monthly
    mp.subscription_cancel_at_period_end = ow.subscription_cancel_at_period_end
    mp.subscription_scheduled_plan = ow.subscription_scheduled_plan
    mp.save(
        update_fields=[
            'subscription_sponsor',
            'subscription_plan',
            'subscription_renewal_at',
            'translation_quota_monthly',
            'subscription_cancel_at_period_end',
            'subscription_scheduled_plan',
        ],
    )


def refresh_seat_hub_after_owner_change(profile: Profile, previous_bundle: str | None = None):
    """
    Après changement du profil titulaire (paiement, renouvellement, etc.).
    Révoque tout si plus éligible ; sinon respecte le plafond d’invités.
    """
    user = profile.user
    mark_expired_invitations_now()

    eligible = owner_eligible_as_seat_hub(profile)
    if not eligible:
        revoke_all_seats_for_owner(user)
        return

    cap = max_invitees_for_bundle(profile.subscription_seat_bundle)
    if cap <= 0:
        revoke_all_seats_for_owner(user)
        return

    with transaction.atomic():
        excess = slots_used(user) - cap
        while excess > 0:
            pend = (
                SubscriptionSeatInvitation.objects.filter(
                    owner=user,
                    status=SubscriptionSeatInvitation.STATUS_PENDING,
                )
                .order_by('-created_at')
                .first()
            )
            if pend:
                pend.status = SubscriptionSeatInvitation.STATUS_REVOKED
                pend.save(update_fields=['status'])
                excess -= 1
                continue
            mem = SubscriptionSeatMember.objects.filter(owner=user).order_by('-created_at').first()
            if mem:
                strip_member_seat_entitlement(mem.member)
                mem.delete()
                excess -= 1
                continue
            break

        sync_member_entitlements_from_owner(user)
