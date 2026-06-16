import logging
import uuid

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from fotos.models import Foto
from fotoce_backend.security.throttling import AuthenticatedUserRateThrottle

from .fedapay_client import create_fedapay_checkout, fedapay_headers, payments_sandbox_allowed
from .models import TipTransaction
from .tip_services import (
    approve_tip_payment,
    get_or_create_wallet,
    recipient_accepts_tips,
    request_withdrawal,
    split_tip_amount,
    tip_config,
    validate_payout_phone,
    validate_tip_amount,
    wallet_payload,
)

logger = logging.getLogger(__name__)


class TipConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cfg = tip_config()
        return Response(
            {
                'commission_percent': cfg.commission_percent,
                'min_tip_amount': cfg.min_tip_amount,
                'max_tip_amount': cfg.max_tip_amount,
                'min_withdrawal_amount': cfg.min_withdrawal_amount,
                'currency_iso': cfg.currency_iso,
                'preset_amounts': [500, 1000, 2000, 5000, 10000],
            },
        )


class TipWalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        if profile.subscription_plan != Profile.PLAN_PRO:
            return Response({'detail': 'Pro plan required'}, status=status.HTTP_403_FORBIDDEN)
        wallet = get_or_create_wallet(request.user)
        recent_tips = (
            TipTransaction.objects.filter(
                recipient=request.user,
                status=TipTransaction.STATUS_APPROVED,
            )
            .order_by('-created_at')[:20]
        )
        withdrawals = request.user.tip_withdrawals.order_by('-created_at')[:15]
        return Response(
            {
                'wallet': wallet_payload(wallet),
                'recent_tips': [
                    {
                        'id': t.id,
                        'amount_gross': t.amount_gross,
                        'amount_net': t.amount_net,
                        'commission_amount': t.commission_amount,
                        'donor_username': t.donor.username,
                        'message': t.message,
                        'foto_slug': t.pin.slug if t.foto_id else None,
                        'created_at': t.created_at.isoformat(),
                    }
                    for t in recent_tips
                ],
                'withdrawals': [
                    {
                        'id': w.id,
                        'amount': w.amount,
                        'status': w.status,
                        'payout_phone': w.payout_phone,
                        'created_at': w.created_at.isoformat(),
                        'processed_at': w.processed_at.isoformat() if w.processed_at else None,
                        'admin_note': w.admin_note,
                    }
                    for w in withdrawals
                ],
            },
        )

    def patch(self, request):
        profile = request.user.profile
        if profile.subscription_plan != Profile.PLAN_PRO:
            return Response({'detail': 'Pro plan required'}, status=status.HTTP_403_FORBIDDEN)
        wallet = get_or_create_wallet(request.user)
        phone = request.data.get('payout_phone')
        label = request.data.get('payout_label')
        if phone is not None:
            err = validate_payout_phone(str(phone))
            if err:
                return Response({'payout_phone': [err]}, status=status.HTTP_400_BAD_REQUEST)
            wallet.payout_phone = str(phone).strip().replace(' ', '').replace('-', '')
        if label is not None:
            wallet.payout_label = str(label).strip()[:80]
        wallet.save(update_fields=['payout_phone', 'payout_label', 'updated_at'])
        return Response({'wallet': wallet_payload(wallet)})


class TipCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AuthenticatedUserRateThrottle]

    def post(self, request):
        recipient_username = (request.data.get('recipient_username') or '').strip()
        if not recipient_username:
            return Response({'error': 'recipient_username is required'}, status=status.HTTP_400_BAD_REQUEST)
        recipient = User.objects.filter(username=recipient_username).select_related('profile').first()
        if not recipient:
            return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)
        if recipient.id == request.user.id:
            return Response({'error': 'Cannot tip yourself'}, status=status.HTTP_400_BAD_REQUEST)
        if not recipient_accepts_tips(recipient):
            return Response({'error': 'Recipient does not accept tips'}, status=status.HTTP_400_BAD_REQUEST)

        amount_raw = request.data.get('amount')
        err = validate_tip_amount(amount_raw)
        if err:
            return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)
        amount_gross = int(amount_raw)

        cfg = tip_config()
        commission, amount_net = split_tip_amount(amount_gross, cfg.commission_percent)

        foto = None
        foto_slug = (request.data.get('foto_slug') or '').strip()
        if foto_slug:
            foto = Foto.objects.filter(slug=foto_slug, author=recipient).first()
            if not foto:
                return Response({'error': 'Foto not found for this creator'}, status=status.HTTP_404_NOT_FOUND)

        message = str(request.data.get('message') or '').strip()[:280]

        tx_ref = f'tip_{uuid.uuid4().hex[:24]}'
        tip = TipTransaction.objects.create(
            donor=request.user,
            recipient=recipient,
            foto=pin,
            amount_gross=amount_gross,
            commission_amount=commission,
            amount_net=amount_net,
            currency_iso=cfg.currency_iso,
            message=message,
            fedapay_transaction_id=tx_ref,
            status=TipTransaction.STATUS_PENDING,
        )

        if not fedapay_headers():
            if payments_sandbox_allowed():
                approve_tip_payment(tip)
                return Response(
                    {
                        'status': 'approved',
                        'tip_id': tip.id,
                        'amount_gross': amount_gross,
                        'commission_amount': commission,
                        'amount_net': amount_net,
                        'sandbox': True,
                    },
                )
            tip.status = TipTransaction.STATUS_CANCELED
            tip.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'Payments not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        from accounts.auth_tokens import checkout_return_url

        callback = checkout_return_url('tip', request=request)
        checkout = create_fedapay_checkout(
            request=request,
            description=f'Pourboire @{recipient.username} via Fotoce',
            amount=amount_gross,
            currency_iso=cfg.currency_iso,
            callback_url=callback,
        )
        if checkout.get('error'):
            tip.status = TipTransaction.STATUS_CANCELED
            tip.save(update_fields=['status', 'updated_at'])
            return Response(checkout, status=status.HTTP_502_BAD_GATEWAY)

        tip.fedapay_transaction_id = checkout['transaction_id']
        tip.save(update_fields=['fedapay_transaction_id', 'updated_at'])
        return Response(
            {
                'status': 'pending',
                'tip_id': tip.id,
                'checkout_url': checkout.get('checkout_url'),
                'transaction_id': checkout['transaction_id'],
                'amount_gross': amount_gross,
                'commission_amount': commission,
                'amount_net': amount_net,
                'commission_percent': cfg.commission_percent,
            },
        )


class TipWithdrawView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile = request.user.profile
        if profile.subscription_plan != Profile.PLAN_PRO:
            return Response({'detail': 'Pro plan required'}, status=status.HTTP_403_FORBIDDEN)
        if not profile.tips_enabled:
            return Response({'detail': 'Tips not enabled'}, status=status.HTTP_403_FORBIDDEN)
        amount_raw = request.data.get('amount')
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            withdrawal = request_withdrawal(request.user, amount)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        wallet = get_or_create_wallet(request.user)
        return Response(
            {
                'withdrawal': {
                    'id': withdrawal.id,
                    'amount': withdrawal.amount,
                    'status': withdrawal.status,
                    'created_at': withdrawal.created_at.isoformat(),
                },
                'wallet': wallet_payload(wallet),
            },
            status=status.HTTP_201_CREATED,
        )


def approve_tip_payment_by_tx(
    transaction_id: str,
    webhook_payload: dict,
    *,
    skip_amount_check: bool = False,
) -> str:
    from monetization.fedapay_webhook import amounts_match, webhook_amount, webhook_status

    tip = TipTransaction.objects.filter(fedapay_transaction_id=transaction_id).first()
    if not tip:
        return 'ignored'
    if tip.status == TipTransaction.STATUS_APPROVED:
        return 'approved'
    if tip.status != TipTransaction.STATUS_PENDING:
        return 'ignored'
    wh_amount = webhook_amount(webhook_payload)
    if not skip_amount_check and not amounts_match(tip.amount_gross, wh_amount):
        return 'amount_mismatch'
    tip.fedapay_payload = {**(tip.fedapay_payload or {}), 'webhook': webhook_payload}
    failed_statuses = {'failed', 'declined', 'rejected', 'canceled', 'cancelled'}
    status_value = webhook_status(webhook_payload)
    if status_value in failed_statuses:
        tip.status = TipTransaction.STATUS_FAILED
        tip.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
        return 'failed'
    approve_tip_payment(tip)
    return 'approved'
