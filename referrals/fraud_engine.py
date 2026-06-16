"""
Moteur anti-fraude referral : vélocité IP/device, cycles, trust, validation différée des récompenses.
Les seuils proviennent du ContestSettings actif (admin concours).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from contests.models import ContestInteractionEvent
from contests.services import get_active_contest_settings, get_referral_settings_for_contest

from .models import (
    ReferralAttribution,
    ReferralAuditLog,
    ReferralEvent,
    ReferralSignupContext,
    ReferralSuspicionFlag,
    UserReferralTrust,
)


def _client_ip(request) -> str:
    if not request:
        return ''
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    if xff:
        return xff[:64]
    return (request.META.get('REMOTE_ADDR') or '')[:64]


def _device_binding(request) -> str:
    if not request:
        return ''
    return (request.META.get('HTTP_X_FOTOCE_DEVICE_BINDING') or '').strip()[:128]


def _ua_snippet(request) -> str:
    if not request:
        return ''
    ua = (request.META.get('HTTP_USER_AGENT') or '')[:240]
    return ua


def _hash_device(request) -> str:
    raw = f'{_device_binding(request)}|{_ua_snippet(request)}'
    if not raw.strip('|'):
        return ''
    return hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:40]


def log_audit(
    *,
    action: str,
    user: User | None = None,
    attribution: ReferralAttribution | None = None,
    request=None,
    metadata: dict | None = None,
) -> None:
    ReferralAuditLog.objects.create(
        user=user,
        attribution=attribution,
        action=action,
        ip=_client_ip(request),
        device_hash=_hash_device(request),
        metadata=metadata or {},
    )


def record_signup_context(user: User, request) -> None:
    ReferralSignupContext.objects.update_or_create(
        user=user,
        defaults={
            'signup_ip': _client_ip(request),
            'device_hash': _hash_device(request),
            'user_agent_snippet': _ua_snippet(request)[:256],
        },
    )


def _active_contest_settings():
    return get_active_contest_settings()


def _active_referral_settings():
    return get_referral_settings_for_contest(_active_contest_settings())


def referee_is_in_uplink_of_referrer(*, referrer_id: int, referee_id: int, max_depth: int = 24) -> bool:
    """Détecte un cycle : le filleul apparaît dans la chaîne « parrains du parrain » (remontée)."""
    if referrer_id == referee_id:
        return True
    uid = referrer_id
    seen: set[int] = set()
    for _ in range(max_depth):
        if uid in seen:
            return True
        seen.add(uid)
        row = (
            ReferralAttribution.objects.filter(referee_id=uid)
            .exclude(status=ReferralAttribution.STATUS_REVOKED)
            .only('referrer_id')
            .first()
        )
        if not row:
            return False
        uid = row.referrer_id
        if uid == referee_id:
            return True


def signup_velocity_allows(*, request, referee: User) -> tuple[bool, str]:
    rs = _active_referral_settings()
    if not rs:
        return True, ''
    since = timezone.now() - timezone.timedelta(hours=24)
    ip = _client_ip(request)
    dev = _hash_device(request)
    if ip:
        max_ip = max(1, int(getattr(rs, 'max_signups_per_ip_per_24h', getattr(rs, 'referral_max_signups_per_ip_per_24h', 40)) or 40))
        n_ip = ReferralSignupContext.objects.filter(signup_ip=ip, created_at__gte=since).exclude(user_id=referee.id).count()
        if n_ip >= max_ip:
            return False, 'ip_velocity'
    if dev:
        max_dev = max(1, int(getattr(rs, 'max_signups_per_device_per_24h', getattr(rs, 'referral_max_signups_per_device_per_24h', 20)) or 20))
        n_dev = ReferralSignupContext.objects.filter(device_hash=dev, created_at__gte=since).exclude(user_id=referee.id).count()
        if n_dev >= max_dev:
            return False, 'device_velocity'
    return True, ''


def open_suspicion(
    *,
    code: str,
    severity: int,
    notes: str,
    user: User | None = None,
    attribution: ReferralAttribution | None = None,
) -> ReferralSuspicionFlag:
    return ReferralSuspicionFlag.objects.create(
        code=code,
        severity=severity,
        notes=notes[:2000],
        user=user,
        attribution=attribution,
        status=ReferralSuspicionFlag.STATUS_OPEN,
    )


def precheck_new_referral(
    *,
    referrer: User,
    referee: User,
    request,
) -> tuple[bool, str]:
    if referrer.id == referee.id:
        return False, 'self_referral'
    if referee_is_in_uplink_of_referrer(referrer_id=referrer.id, referee_id=referee.id):
        log_audit(action='circular_referral_blocked', user=referee, metadata={'referrer_id': referrer.id}, request=request)
        open_suspicion(
            code='circular_referral',
            severity=4,
            notes='Tentative de parrainage circulaire',
            user=referee,
            attribution=None,
        )
        return False, 'circular_referral'
    ok, reason = signup_velocity_allows(request=request, referee=referee)
    if not ok:
        log_audit(action=f'velocity_{reason}', user=referee, metadata={'referrer_id': referrer.id}, request=request)
        open_suspicion(code=reason, severity=2, notes='Vélocité inscription', user=referee)
        return False, reason
    return True, ''


def compute_and_store_referee_trust(referee: User) -> float:
    """Heuristique légère mais extensible (signaux JSON)."""
    score = 0.42
    signals: dict[str, Any] = {}
    from allauth.account.models import EmailAddress

    if EmailAddress.objects.filter(user=referee, verified=True).exists():
        score += 0.18
        signals['email_verified'] = True
    try:
        prof = referee.profile
        if getattr(prof, 'birth_date', None):
            score += 0.08
            signals['birth_date'] = True
        if prof.avatar:
            score += 0.04
            signals['avatar'] = True
    except Exception:
        pass

    n_inter = ContestInteractionEvent.objects.filter(actor_id=referee.id, is_valid=True).count()
    score += min(0.28, 0.02 * float(n_inter))
    signals['valid_contest_interactions'] = n_inter

    age_h = max(0.0, (timezone.now() - referee.date_joined).total_seconds() / 3600.0)
    score += min(0.12, 0.002 * age_h)

    score = max(0.05, min(0.98, score))
    UserReferralTrust.objects.update_or_create(
        user=referee,
        defaults={'score': score, 'signals_json': signals},
    )
    return score


def count_referee_valid_contest_actions(*, referee_id: int, contest_id: int | None) -> int:
    if not contest_id:
        return ContestInteractionEvent.objects.filter(actor_id=referee_id, is_valid=True).count()
    return ContestInteractionEvent.objects.filter(actor_id=referee_id, contest_id=contest_id, is_valid=True).count()


def has_open_blocking_suspicion_for_attribution(attr: ReferralAttribution) -> bool:
    return ReferralSuspicionFlag.objects.filter(
        Q(attribution_id=attr.pk) | Q(user_id=attr.referee_id),
        status=ReferralSuspicionFlag.STATUS_OPEN,
        severity__gte=4,
    ).exists()


def evaluate_referral_reward_eligibility(attr: ReferralAttribution) -> tuple[bool, str]:
    if attr.rewards_granted_at:
        return False, 'already_granted'
    if attr.status == ReferralAttribution.STATUS_REVOKED:
        return False, 'revoked'
    if attr.status != ReferralAttribution.STATUS_ACTIVE:
        return False, 'not_active'
    if has_open_blocking_suspicion_for_attribution(attr):
        return False, 'suspicion_open'
    if not attr.email_verified_at:
        return False, 'email_not_marked'

    rs = _active_referral_settings()
    if not rs:
        return False, 'no_contest'
    if not bool(getattr(rs, 'defer_rewards', getattr(rs, 'referral_defer_rewards', True))):
        return True, 'defer_disabled'

    referee = User.objects.get(pk=attr.referee_id)
    trust = compute_and_store_referee_trust(referee)
    th = float(getattr(rs, 'referee_trust_threshold', getattr(rs, 'referral_referee_trust_threshold', 0.25)) or 0.25)
    if trust < th:
        return False, f'trust_below:{trust:.2f}<{th:.2f}'

    min_age_h = max(0, int(getattr(rs, 'min_account_age_hours', getattr(rs, 'referral_min_account_age_hours', 12)) or 0))
    age_h = (timezone.now() - referee.date_joined).total_seconds() / 3600.0
    if age_h < min_age_h:
        return False, 'account_too_young'

    delay_h = max(0, int(getattr(rs, 'reward_delay_hours', getattr(rs, 'referral_reward_delay_hours', 1)) or 0))
    if delay_h and attr.email_verified_at and (timezone.now() - attr.email_verified_at).total_seconds() < delay_h * 3600:
        return False, 'reward_delay'

    min_days = max(0, int(getattr(rs, 'min_days_before_reward', getattr(rs, 'referral_min_days_before_reward', 2)) or 0))
    if min_days and attr.activated_at and (timezone.now() - attr.activated_at).days < min_days:
        return False, 'min_days_not_met'

    min_act = max(0, int(getattr(rs, 'min_engagement_actions', getattr(rs, 'referral_min_engagement_actions', 1)) or 0))
    if min_act:
        contest = _active_contest_settings()
        n = count_referee_valid_contest_actions(referee_id=referee.id, contest_id=getattr(contest, 'id', None))
        if n < min_act:
            return False, f'actions:{n}<{min_act}'

    min_pins = max(0, int(getattr(rs, 'min_pins_published', getattr(rs, 'referral_min_pins_published', 0)) or 0))
    if min_pins:
        from fotos.models import Foto

        n_pins = Foto.objects.filter(
            author_id=referee.id,
            visibility=Foto.VISIBILITY_PUBLIC,
            is_story=False,
        ).count()
        if n_pins < min_pins:
            return False, f'pins:{n_pins}<{min_pins}'

    return True, 'ok'


def signup_fingerprint(request) -> tuple[str, str]:
    return _client_ip(request), _hash_device(request)


def describe_deferral_for_contest(contest) -> dict[str, Any]:
    rs = get_referral_settings_for_contest(contest)
    if not rs:
        return {'defer': True}
    return {
        'defer': bool(getattr(rs, 'defer_rewards', getattr(rs, 'referral_defer_rewards', True))),
        'min_account_age_hours': int(getattr(rs, 'min_account_age_hours', getattr(rs, 'referral_min_account_age_hours', 12)) or 0),
        'min_engagement_actions': int(getattr(rs, 'min_engagement_actions', getattr(rs, 'referral_min_engagement_actions', 1)) or 0),
        'reward_delay_hours': int(getattr(rs, 'reward_delay_hours', getattr(rs, 'referral_reward_delay_hours', 1)) or 0),
        'min_days_before_reward': int(getattr(rs, 'min_days_before_reward', getattr(rs, 'referral_min_days_before_reward', 2)) or 0),
        'trust_threshold': float(getattr(rs, 'referee_trust_threshold', getattr(rs, 'referral_referee_trust_threshold', 0.25)) or 0.25),
    }
