"""
API groupe famille / petite équipe (invitations, membres).

Toutes les vérifications d’élégibilité sont côté serveur (doublons, plafonds, sponsorisation).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .subscription_utils import _enforce_subscription_state
from .subscription_seats import (
    SUBSCRIPTION_BUNDLE_FAMILY,
    SUBSCRIPTION_BUNDLE_TEAM,
    SUBSCRIPTION_SEAT_INVITE_EXPIRY_HOURS,
    grant_member_seat,
    invitee_eligible,
    generate_invite_plain_token_and_hash,
    mark_expired_invitations_now,
    max_invitees_for_bundle,
    owner_eligible_as_seat_hub,
    revoke_all_seats_for_owner,
    slots_used,
    strip_member_seat_entitlement,
)
from .models import Profile, SubscriptionSeatInvitation, SubscriptionSeatMember


def _invite_create_rate_allow(owner_user: User) -> bool:
    cutoff = timezone.now() - timedelta(hours=1)
    n = SubscriptionSeatInvitation.objects.filter(owner=owner_user, created_at__gte=cutoff).count()
    return n < 40


GENERIC_DENY_MSG = 'Action impossible avec ces paramètres.'


class SubscriptionSeatsOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        _enforce_subscription_state(profile)
        profile.refresh_from_db()
        user = request.user
        mark_expired_invitations_now()

        pending_incoming = SubscriptionSeatInvitation.objects.filter(
            invitee=user,
            status=SubscriptionSeatInvitation.STATUS_PENDING,
            expires_at__gte=timezone.now(),
        ).select_related('owner', 'owner__profile')
        incoming_list = [
            {
                'id': str(inv.id),
                'owner_username': inv.owner.username,
                'owner_display_name': inv.owner.profile.display_name or inv.owner.username,
                'expires_at': inv.expires_at.isoformat(),
            }
            for inv in pending_incoming.order_by('-created_at')
        ]

        if profile.subscription_sponsor_id:
            sp = profile.subscription_sponsor
            return Response(
                {
                    'role': 'member',
                    'sponsor_username': sp.username if sp else None,
                    'sponsor_display_name': (sp.profile.display_name or sp.username) if sp else None,
                    'seat_plan': profile.subscription_plan,
                    'incoming_invitations': incoming_list,
                }
            )

        if owner_eligible_as_seat_hub(profile):
            cap = max_invitees_for_bundle(profile.subscription_seat_bundle)
            mems = SubscriptionSeatMember.objects.filter(owner=user).select_related('member__profile')
            pend = SubscriptionSeatInvitation.objects.filter(
                owner=user,
                status=SubscriptionSeatInvitation.STATUS_PENDING,
                expires_at__gte=timezone.now(),
            ).select_related('invitee__profile')

            return Response(
                {
                    'role': 'owner',
                    'seat_bundle': profile.subscription_seat_bundle,
                    'max_invitees': cap,
                    'used_slots': slots_used(user),
                    'members': [
                        {
                            'username': row.member.username,
                            'display_name': row.member.profile.display_name or row.member.username,
                            'joined_at': row.joined_at.isoformat(),
                        }
                        for row in mems.order_by('-joined_at')
                    ],
                    'pending_invitations': [
                        {
                            'id': str(inv.id),
                            'invitee_username': inv.invitee.username,
                            'expires_at': inv.expires_at.isoformat(),
                            'created_at': inv.created_at.isoformat(),
                        }
                        for inv in pend.order_by('-created_at')
                    ],
                    'incoming_invitations': incoming_list,
                }
            )

        return Response({'role': 'none', 'seat_bundle': profile.subscription_seat_bundle or 'solo', 'incoming_invitations': incoming_list})


class SubscriptionSeatInviteCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        username = str(request.data.get('username') or '').strip().lstrip('@')
        if len(username) < 2:
            return Response({'error': 'username requis.'}, status=status.HTTP_400_BAD_REQUEST)

        owner = request.user
        profile = owner.profile
        _enforce_subscription_state(profile)
        profile.refresh_from_db()

        if profile.subscription_sponsor_id:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_403_FORBIDDEN)
        if not owner_eligible_as_seat_hub(profile):
            return Response({'error': 'Offre famille ou équipe non active.'}, status=status.HTTP_403_FORBIDDEN)
        if not _invite_create_rate_allow(owner):
            return Response({'error': 'Trop d’invitations récentes. Réessayez plus tard.'}, status=429)

        try:
            target = User.objects.select_related('profile').get(username__iexact=username)
        except User.DoesNotExist:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_404_NOT_FOUND)

        if target.id == owner.id:
            return Response({'error': 'Vous ne pouvez pas vous inviter vous-même.'}, status=status.HTTP_400_BAD_REQUEST)

        _enforce_subscription_state(target.profile)
        target.profile.refresh_from_db()
        ip = target.profile

        mark_expired_invitations_now()

        cap = max_invitees_for_bundle(profile.subscription_seat_bundle)
        if slots_used(owner) >= cap:
            return Response({'error': 'Nombre maximum de sièges atteint.'}, status=status.HTTP_409_CONFLICT)

        if not invitee_eligible(ip):
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_400_BAD_REQUEST)

        _plain_token, digest = generate_invite_plain_token_and_hash()
        expires = timezone.now() + timedelta(hours=SUBSCRIPTION_SEAT_INVITE_EXPIRY_HOURS)

        try:
            with transaction.atomic():
                inv = SubscriptionSeatInvitation.objects.create(
                    owner=owner,
                    invitee=target,
                    token_hash=digest,
                    status=SubscriptionSeatInvitation.STATUS_PENDING,
                    expires_at=expires,
                )
        except IntegrityError:
            return Response({'error': 'Une invitation vers ce membre existe déjà.'}, status=status.HTTP_409_CONFLICT)

        from notifications.notification_i18n import create_localized_notification

        bundle_kind = str(profile.subscription_seat_bundle or '').strip().lower()
        if bundle_kind == SUBSCRIPTION_BUNDLE_TEAM:
            notif_title = 'Invitation abonnement Équipe'
            notif_message = (
                f'{owner.username} vous invite dans son abonnement Pinova Équipe '
                f'(plusieurs sièges sur une même facturation).'
            )
        elif bundle_kind == SUBSCRIPTION_BUNDLE_FAMILY:
            notif_title = 'Invitation abonnement Famille'
            notif_message = (
                f'{owner.username} vous invite dans son abonnement Pinova Famille '
                f'(plusieurs sièges sur une même facturation).'
            )
        else:
            notif_title = 'Invitation abonnement groupe'
            notif_message = (
                f'{owner.username} vous invite dans son abonnement Pinova famille ou équipe.'
            )

        create_localized_notification(
            recipient=target,
            sender=owner,
            notification_type='system',
            title_fr=notif_title,
            message_fr=notif_message,
            action_url='/settings',
            metadata={
                'seat_invite_id': str(inv.id),
                'kind': 'subscription_seat_invite',
                'seat_bundle': bundle_kind or profile.subscription_seat_bundle,
            },
        )
        # token_hash conserve une empreinte en base pour d’éventuels audits ; l’acceptation
        # ne repose que sur l’utilisateur authentifié (comme les invitations board collaboratif).
        return Response(
            {
                'id': str(inv.id),
                'expires_at': inv.expires_at.isoformat(),
                'invitee_username': target.username,
            },
            status=status.HTTP_201_CREATED,
        )


class SubscriptionSeatInviteDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, invite_id):
        """Titulaire : révoque une invitation encore en attente."""
        owner = request.user
        mark_expired_invitations_now()
        inv = SubscriptionSeatInvitation.objects.filter(id=invite_id, owner=owner).first()
        if not inv or inv.status != SubscriptionSeatInvitation.STATUS_PENDING:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_404_NOT_FOUND)
        inv.status = SubscriptionSeatInvitation.STATUS_REVOKED
        inv.responded_at = timezone.now()
        inv.save(update_fields=['status', 'responded_at'])
        return Response({'status': 'revoked'})

    def post(self, request, invite_id):
        """Invité uniquement — accepter ou refuser avec body { \"action\": accept|decline }."""
        action = str(request.data.get('action') or '').strip().lower()
        if action not in {'accept', 'decline'}:
            return Response({'error': 'action invalide'}, status=status.HTTP_400_BAD_REQUEST)

        mark_expired_invitations_now()
        inv = (
            SubscriptionSeatInvitation.objects.select_related('owner', 'owner__profile', 'invitee')
            .filter(id=invite_id, invitee=request.user)
            .first()
        )
        if (
            not inv
            or inv.status != SubscriptionSeatInvitation.STATUS_PENDING
            or inv.expires_at < timezone.now()
        ):
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_404_NOT_FOUND)

        if action == 'decline':
            with transaction.atomic():
                inv_locked = SubscriptionSeatInvitation.objects.select_for_update().filter(
                    pk=inv.pk,
                    invitee=request.user,
                ).first()
                if (
                    inv_locked
                    and inv_locked.status == SubscriptionSeatInvitation.STATUS_PENDING
                ):
                    inv_locked.status = SubscriptionSeatInvitation.STATUS_DECLINED
                    inv_locked.responded_at = timezone.now()
                    inv_locked.save(update_fields=['status', 'responded_at'])
            return Response({'status': 'declined'})

        try:
            with transaction.atomic():
                inv_locked = SubscriptionSeatInvitation.objects.select_for_update().get(
                    pk=inv.pk,
                    invitee=request.user,
                )
                if inv_locked.status != SubscriptionSeatInvitation.STATUS_PENDING:
                    raise ValueError('conflict_state')
                grant_member_seat(inv_locked.owner, inv_locked.invitee)
                inv_locked.status = SubscriptionSeatInvitation.STATUS_ACCEPTED
                inv_locked.responded_at = timezone.now()
                inv_locked.save(update_fields=['status', 'responded_at'])
        except (ValueError, SubscriptionSeatInvitation.DoesNotExist, IntegrityError):
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_409_CONFLICT)

        return Response({'status': 'accepted'})


class SubscriptionSeatMemberRemoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, username):
        username = username.strip().lstrip('@')
        owner = request.user
        profile = owner.profile
        _enforce_subscription_state(profile)
        profile.refresh_from_db()
        if not owner_eligible_as_seat_hub(profile):
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_403_FORBIDDEN)
        tgt = User.objects.filter(username__iexact=username).first()
        if not tgt:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_404_NOT_FOUND)
        row = SubscriptionSeatMember.objects.filter(owner=owner, member=tgt).first()
        if not row:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            strip_member_seat_entitlement(tgt)
            row.delete()
        return Response({'status': 'removed'})


class SubscriptionSeatLeaveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        sponsor_id = getattr(user.profile, 'subscription_sponsor_id', None)
        if not sponsor_id:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            SubscriptionSeatMember.objects.filter(owner_id=sponsor_id, member=user).delete()
            strip_member_seat_entitlement(user)
        return Response({'status': 'left'})


class SubscriptionSeatAdminRevokeHubView(APIView):
    """Secours administratif : révoquer tout sur un groupe (titulaire)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        owner = request.user
        profile = owner.profile
        _enforce_subscription_state(profile)
        profile.refresh_from_db()
        if profile.subscription_sponsor_id:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_403_FORBIDDEN)
        if profile.subscription_plan not in {Profile.PLAN_PLUS, Profile.PLAN_PRO}:
            return Response({'error': GENERIC_DENY_MSG}, status=status.HTTP_403_FORBIDDEN)

        revoke_all_seats_for_owner(owner)
        return Response({'status': 'all_revoked'})
