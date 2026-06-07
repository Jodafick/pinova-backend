"""Traitement métier des webhooks FedaPay (abonnement, tip, boost)."""

from __future__ import annotations

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from pinova_backend.observability.analytics import (
    capture_boost_purchased,
    capture_campaign_launched,
    capture_checkout_success,
    capture_tip_sent,
)
from accounts.models import SubscriptionPayment

from .fedapay_webhook import (
    APPROVED_STATUSES,
    CANCELED_STATUSES,
    FAILED_STATUSES,
    amount_mismatch_response,
    amounts_match,
    is_webhook_replay,
    log_webhook_event,
    mark_webhook_processed,
    normalize_transaction_body,
    replay_response,
    webhook_amount,
    webhook_status,
    webhook_transaction_id,
)
from .tip_views import approve_tip_payment_by_tx
from .views import approve_boost_payment


def _event_type(flow: str, status_value: str) -> str:
    return f'{flow}.{status_value or "unknown"}'


def handle_fedapay_webhook_payload(payload: dict) -> Response:
    tx_id = webhook_transaction_id(payload)
    if not tx_id:
        return Response({'error': 'transaction_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    status_value = webhook_status(payload)
    wh_amount = webhook_amount(payload)

    payment = SubscriptionPayment.objects.filter(fedapay_transaction_id=tx_id).select_related(
        'user', 'user__profile'
    ).first()
    if payment:
        return _handle_subscription_webhook(payment, payload, tx_id, status_value, wh_amount)

    if status_value in APPROVED_STATUSES:
        tip_result = _handle_tip_webhook(payload, tx_id, status_value, wh_amount)
        if tip_result is not None:
            return tip_result
        boost_result = _handle_boost_webhook(payload, tx_id, status_value, wh_amount)
        if boost_result is not None:
            return boost_result

    log_webhook_event(
        flow='unknown',
        status='ignored',
        transaction_id=tx_id,
        user_id=None,
        amount=wh_amount,
        extra={'webhook_status': status_value},
    )
    return Response({'status': 'ignored_unknown_transaction'}, status=status.HTTP_202_ACCEPTED)


def _handle_subscription_webhook(payment, payload, tx_id, status_value, wh_amount):
    from accounts.views import (
        SubscriptionConfirmView,
        _catalog_entry,
        _extract_invoice_url_from_fedapay,
        _normalized_seat_bundle,
    )

    flow = 'subscription'
    event_type = _event_type(flow, status_value or payment.status)

    if is_webhook_replay(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    if status_value in APPROVED_STATUSES and not amounts_match(payment.amount, wh_amount):
        return amount_mismatch_response(
            flow=flow,
            transaction_id=tx_id,
            user_id=payment.user_id,
            expected=payment.amount,
            received=wh_amount,
        )

    if not mark_webhook_processed(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    payload_store = dict(payment.fedapay_payload or {})
    payload_store['webhook'] = payload
    payment.fedapay_payload = payload_store

    if status_value in APPROVED_STATUSES:
        seat_bundle_pay = _normalized_seat_bundle(payment.promo_bundle)
        catalog = _catalog_entry(payment.plan, payment.billing_cycle, seat_bundle_pay)
        duration_days = int((catalog or {}).get('duration_days') or 30)
        previous_plan = payment.user.profile.subscription_plan
        payment.status = SubscriptionPayment.STATUS_APPROVED
        normalized_wh = normalize_transaction_body(payload)
        invoice_wh = _extract_invoice_url_from_fedapay(normalized_wh)
        uf = ['status', 'fedapay_payload', 'updated_at']
        if invoice_wh:
            payment.invoice_url = invoice_wh
            uf.append('invoice_url')
        with transaction.atomic():
            payment.save(update_fields=uf)
            SubscriptionConfirmView()._apply_subscription(payment.user.profile, payment, duration_days)
            SubscriptionConfirmView()._notify_payment_events(payment.user, payment, previous_plan)
        log_webhook_event(
            flow=flow,
            status='approved',
            transaction_id=tx_id,
            user_id=payment.user_id,
            amount=wh_amount or payment.amount,
        )
        capture_checkout_success(
            user_id=payment.user_id,
            flow='premium',
            amount=wh_amount or payment.amount,
            currency=getattr(payment, 'currency_iso', 'XOF') or 'XOF',
            transaction_id=tx_id,
        )
        return Response({'status': 'approved', 'flow': flow})

    if status_value in CANCELED_STATUSES:
        payment.status = SubscriptionPayment.STATUS_CANCELED
    elif status_value in FAILED_STATUSES:
        payment.status = SubscriptionPayment.STATUS_FAILED
    else:
        payment.status = SubscriptionPayment.STATUS_PENDING
    payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
    log_webhook_event(
        flow=flow,
        status=payment.status,
        transaction_id=tx_id,
        user_id=payment.user_id,
        amount=wh_amount or payment.amount,
    )
    return Response({'status': payment.status, 'flow': flow})


def _handle_tip_webhook(payload, tx_id, status_value, wh_amount):
    from .models import TipTransaction

    tip = TipTransaction.objects.filter(fedapay_transaction_id=tx_id).first()
    if not tip:
        return None

    flow = 'tip'
    event_type = _event_type(flow, status_value or tip.status)

    if is_webhook_replay(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    if status_value in APPROVED_STATUSES and not amounts_match(tip.amount_gross, wh_amount):
        return amount_mismatch_response(
            flow=flow,
            transaction_id=tx_id,
            user_id=tip.recipient_id,
            expected=tip.amount_gross,
            received=wh_amount,
        )

    if not mark_webhook_processed(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    result = approve_tip_payment_by_tx(tx_id, payload, skip_amount_check=True)
    log_webhook_event(
        flow=flow,
        status=result,
        transaction_id=tx_id,
        user_id=tip.recipient_id,
        amount=wh_amount or tip.amount_gross,
    )
    if result == 'approved':
        capture_tip_sent(
            sender_id=tip.donor_id,
            amount=wh_amount or tip.amount_gross,
            recipient_id=tip.recipient_id,
        )
        capture_checkout_success(
            user_id=tip.donor_id,
            flow='tip',
            amount=wh_amount or tip.amount_gross,
            currency=tip.currency_iso or 'XOF',
            transaction_id=tx_id,
        )
        return Response({'status': 'tip_approved', 'flow': flow})
    return Response({'status': result, 'flow': flow}, status=status.HTTP_200_OK)


def _handle_boost_webhook(payload, tx_id, status_value, wh_amount):
    from .models import PinBoost, PinPromoCampaign

    promo = PinPromoCampaign.objects.filter(fedapay_transaction_id=tx_id).select_related('package').first()
    boost = PinBoost.objects.filter(fedapay_transaction_id=tx_id).select_related('package').first()
    if not promo and not boost:
        return None

    flow = 'boost'
    event_type = _event_type(flow, status_value or 'approved')

    if is_webhook_replay(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    expected = (promo or boost).package.amount
    owner_id = (promo or boost).owner_id
    if status_value in APPROVED_STATUSES and not amounts_match(expected, wh_amount):
        return amount_mismatch_response(
            flow=flow,
            transaction_id=tx_id,
            user_id=owner_id,
            expected=expected,
            received=wh_amount,
        )

    if not mark_webhook_processed(tx_id, event_type):
        return replay_response(flow, tx_id, event_type)

    result = approve_boost_payment(tx_id, payload, skip_amount_check=True)
    log_webhook_event(
        flow=flow,
        status=result,
        transaction_id=tx_id,
        user_id=owner_id,
        amount=wh_amount or expected,
    )
    if result == 'approved':
        amount = wh_amount or expected
        if promo:
            capture_campaign_launched(
                user_id=owner_id,
                campaign_id=promo.id,
                amount=amount,
            )
            capture_checkout_success(
                user_id=owner_id,
                flow='campaign',
                amount=amount,
                transaction_id=tx_id,
            )
        elif boost:
            capture_boost_purchased(user_id=owner_id, amount=amount, pin_id=boost.pin_id)
            capture_checkout_success(
                user_id=owner_id,
                flow='boost',
                amount=amount,
                transaction_id=tx_id,
            )
        return Response({'status': 'boost_approved', 'flow': flow})
    return Response({'status': result, 'flow': flow}, status=status.HTTP_200_OK)
