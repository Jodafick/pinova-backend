"""
Calcul et structure des lignes de monétisation (primes podium) pour les concours pins et referral.

Les montants reposent sur `ContestSettings`: mode fixed / percentage / custom, `total_prize_pool`,
`winner_*_amount`, `distribution_weights_json`.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.utils import timezone

from .models import ContestSettings, ContestWinnerPayout


DEC2 = Decimal('0.01')
ZERO = Decimal('0')
DEFAULT_CURRENCY = 'EUR'


def compute_rank_prize_amounts(contest: ContestSettings) -> dict[int, Decimal]:
    """
    Montant brut par rang (1-based) jusqu'à `max_winners`, selon la configuration du concours.
    Les rangs sans lauréat restent hors `payout_json` mais peuvent représenter une enveloppe non attribuée.
    """
    slots = max(1, min(int(contest.max_winners or 1), 255))
    pool = ZERO if contest.total_prize_pool is None else Decimal(contest.total_prize_pool)
    pool = pool.quantize(DEC2, rounding=ROUND_HALF_UP)
    mode = contest.distribution_mode

    if pool <= ZERO:
        return {rank: ZERO for rank in range(1, slots + 1)}

    if mode == ContestSettings.DISTRIBUTION_FIXED:
        fixed_by_rank = {
            1: contest.winner_1_amount,
            2: contest.winner_2_amount,
            3: contest.winner_3_amount,
        }
        return {
            rank: (Decimal(fixed_by_rank.get(rank) or ZERO)).quantize(DEC2, ROUND_HALF_UP)
            for rank in range(1, slots + 1)
        }

    weights = contest.distribution_weights_json or []

    if mode == ContestSettings.DISTRIBUTION_CUSTOM:
        amounts: list[Decimal] = []
        for i in range(slots):
            if i < len(weights):
                raw = weights[i]
                try:
                    amounts.append(Decimal(str(raw)).quantize(DEC2, ROUND_HALF_UP))
                except Exception:
                    amounts.append(ZERO)
            else:
                amounts.append(ZERO)
        return {rank: amounts[rank - 1] for rank in range(1, slots + 1)}

    # Percentage mode
    pct_list: list[Decimal] = []
    for i in range(slots):
        if i < len(weights):
            try:
                pct_list.append(Decimal(str(weights[i])))
            except Exception:
                pct_list.append(ZERO)
        else:
            pct_list.append(ZERO)

    if sum(pct_list, ZERO) <= ZERO:
        return {rank: ZERO for rank in range(1, slots + 1)}

    amounts_pct: list[Decimal] = []
    for pct in pct_list:
        chunk = (pool * pct / Decimal('100')).quantize(DEC2, ROUND_HALF_UP)
        amounts_pct.append(chunk)

    drift = pool - sum(amounts_pct, ZERO)
    if drift != ZERO and amounts_pct:
        amounts_pct[-1] = (amounts_pct[-1] + drift).quantize(DEC2, ROUND_HALF_UP)

    return {rank: amounts_pct[rank - 1] for rank in range(1, slots + 1)}


def build_pin_contest_payout_payload(contest: ContestSettings, winners: list[dict[str, Any]]):
    """Retourne (payout_json, instances `ContestWinnerPayout` à persister pour le concours pins)."""
    rank_amounts = compute_rank_prize_amounts(contest)
    now_iso = timezone.now().isoformat()
    lines: list[dict[str, Any]] = []
    rows: list[ContestWinnerPayout] = []

    for w in winners:
        rank = int(w['rank'])
        uid = int(w['creator_id'])
        pin_id_raw = w.get('pin_id')
        pin_id = int(pin_id_raw) if pin_id_raw is not None else None
        gross = rank_amounts.get(rank, ZERO)

        line = {
            'rank': rank,
            'gross_amount': str(gross),
            'currency': DEFAULT_CURRENCY,
            'distribution_mode': contest.distribution_mode,
            'beneficiary_user_id': uid,
            'pin_id': pin_id,
            'computed_at': now_iso,
        }
        lines.append(line)
        rows.append(
            ContestWinnerPayout(
                contest=contest,
                source=ContestWinnerPayout.SOURCE_PINS,
                winner_rank=rank,
                beneficiary_id=uid,
                pin_id=pin_id,
                gross_amount=gross,
                currency=DEFAULT_CURRENCY,
                payment_status=ContestWinnerPayout.STATUS_PENDING,
            )
        )
    return lines, rows


def build_referral_contest_payout_payload(contest: ContestSettings, winners: list[dict[str, Any]]):
    """Même logique financière ; bénéficiaire = referrer, sans pin."""
    rank_amounts = compute_rank_prize_amounts(contest)
    now_iso = timezone.now().isoformat()
    lines: list[dict[str, Any]] = []
    rows: list[ContestWinnerPayout] = []

    for w in winners:
        rank = int(w['rank'])
        uid = int(w['referrer_id'])
        gross = rank_amounts.get(rank, ZERO)

        line = {
            'rank': rank,
            'gross_amount': str(gross),
            'currency': DEFAULT_CURRENCY,
            'distribution_mode': contest.distribution_mode,
            'beneficiary_user_id': uid,
            'computed_at': now_iso,
        }
        lines.append(line)
        rows.append(
            ContestWinnerPayout(
                contest=contest,
                source=ContestWinnerPayout.SOURCE_REFERRAL,
                winner_rank=rank,
                beneficiary_id=uid,
                pin_id=None,
                gross_amount=gross,
                currency=DEFAULT_CURRENCY,
                payment_status=ContestWinnerPayout.STATUS_PENDING,
            )
        )
    return lines, rows
