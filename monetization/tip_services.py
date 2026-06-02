from __future__ import annotations

import re

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile

from .models import CreatorWallet, TipPlatformConfig, TipTransaction, TipWithdrawal

PHONE_RE = re.compile(r'^\+?[0-9]{8,16}$')


def tip_config() -> TipPlatformConfig:
    return TipPlatformConfig.load()


def split_tip_amount(amount_gross: int, commission_percent: int) -> tuple[int, int]:
    gross = max(0, int(amount_gross))
    pct = max(0, min(100, int(commission_percent)))
    commission = gross * pct // 100
    if commission < 1 and gross > 0 and pct > 0:
        commission = 1
    if commission > gross:
        commission = gross
    return commission, gross - commission


def recipient_accepts_tips(user: User) -> bool:
    profile = user.profile
    return (
        profile.subscription_plan == Profile.PLAN_PRO
        and profile.tips_enabled
    )


def get_or_create_wallet(user: User) -> CreatorWallet:
    cfg = tip_config()
    wallet, _ = CreatorWallet.objects.get_or_create(
        user=user,
        defaults={'currency_iso': cfg.currency_iso},
    )
    return wallet


def wallet_payload(wallet: CreatorWallet) -> dict:
    cfg = tip_config()
    return {
        'balance_available': wallet.balance_available,
        'balance_reserved': wallet.balance_reserved,
        'currency_iso': wallet.currency_iso,
        'total_received_gross': wallet.total_received_gross,
        'total_received_net': wallet.total_received_net,
        'total_withdrawn': wallet.total_withdrawn,
        'payout_phone': wallet.payout_phone,
        'payout_label': wallet.payout_label,
        'commission_percent': cfg.commission_percent,
        'min_tip_amount': cfg.min_tip_amount,
        'max_tip_amount': cfg.max_tip_amount,
        'min_withdrawal_amount': cfg.min_withdrawal_amount,
    }


def validate_tip_amount(amount: int) -> str | None:
    cfg = tip_config()
    try:
        val = int(amount)
    except (TypeError, ValueError):
        return 'Invalid amount'
    if val < cfg.min_tip_amount:
        return f'Minimum tip is {cfg.min_tip_amount} {cfg.currency_iso}'
    if val > cfg.max_tip_amount:
        return f'Maximum tip is {cfg.max_tip_amount} {cfg.currency_iso}'
    return None


def validate_payout_phone(phone: str) -> str | None:
    raw = (phone or '').strip().replace(' ', '').replace('-', '')
    if not raw or not PHONE_RE.match(raw):
        return 'Invalid payout phone number'
    return None


@transaction.atomic
def approve_tip_payment(tip: TipTransaction) -> bool:
    if tip.status == TipTransaction.STATUS_APPROVED:
        return True
    if tip.status != TipTransaction.STATUS_PENDING:
        return False
    wallet = CreatorWallet.objects.select_for_update().get_or_create(
        user=tip.recipient,
        defaults={'currency_iso': tip.currency_iso},
    )[0]
    wallet.balance_available += tip.amount_net
    wallet.total_received_gross += tip.amount_gross
    wallet.total_received_net += tip.amount_net
    wallet.save(
        update_fields=[
            'balance_available',
            'total_received_gross',
            'total_received_net',
            'updated_at',
        ],
    )
    tip.status = TipTransaction.STATUS_APPROVED
    tip.save(update_fields=['status', 'updated_at'])
    return True


@transaction.atomic
def request_withdrawal(user: User, amount: int) -> TipWithdrawal:
    cfg = tip_config()
    amt = int(amount)
    if amt < cfg.min_withdrawal_amount:
        raise ValueError(f'Minimum withdrawal is {cfg.min_withdrawal_amount} {cfg.currency_iso}')
    wallet = CreatorWallet.objects.select_for_update().get(
        user=user,
    )
    if not wallet.payout_phone.strip():
        raise ValueError('Payout phone is required')
    if amt > wallet.balance_available:
        raise ValueError('Insufficient balance')
    wallet.balance_available -= amt
    wallet.balance_reserved += amt
    wallet.save(update_fields=['balance_available', 'balance_reserved', 'updated_at'])
    return TipWithdrawal.objects.create(
        user=user,
        amount=amt,
        currency_iso=wallet.currency_iso,
        payout_phone=wallet.payout_phone.strip(),
        payout_label=wallet.payout_label.strip(),
        status=TipWithdrawal.STATUS_PENDING,
    )


@transaction.atomic
def mark_withdrawal_paid(withdrawal: TipWithdrawal) -> None:
    if withdrawal.status == TipWithdrawal.STATUS_PAID:
        return
    wallet = CreatorWallet.objects.select_for_update().get(user=withdrawal.user)
    if withdrawal.status == TipWithdrawal.STATUS_PENDING:
        if wallet.balance_reserved < withdrawal.amount:
            raise ValueError('Reserved balance mismatch')
    withdrawal.status = TipWithdrawal.STATUS_PAID
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=['status', 'processed_at', 'updated_at'])
    wallet.balance_reserved = max(0, wallet.balance_reserved - withdrawal.amount)
    wallet.total_withdrawn += withdrawal.amount
    wallet.save(update_fields=['balance_reserved', 'total_withdrawn', 'updated_at'])


@transaction.atomic
def reject_withdrawal(withdrawal: TipWithdrawal, admin_note: str = '') -> None:
    if withdrawal.status in {TipWithdrawal.STATUS_PAID, TipWithdrawal.STATUS_REJECTED}:
        return
    wallet = CreatorWallet.objects.select_for_update().get(user=withdrawal.user)
    wallet.balance_available += withdrawal.amount
    wallet.balance_reserved = max(0, wallet.balance_reserved - withdrawal.amount)
    wallet.save(update_fields=['balance_available', 'balance_reserved', 'updated_at'])
    withdrawal.status = TipWithdrawal.STATUS_REJECTED
    withdrawal.admin_note = (admin_note or '')[:400]
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=['status', 'admin_note', 'processed_at', 'updated_at'])
