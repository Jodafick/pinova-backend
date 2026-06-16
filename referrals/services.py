from __future__ import annotations

import re
import secrets
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from contests.services import get_active_contest_settings, get_referral_settings_for_contest

from .antifraud import is_self_referral, should_reject_low_trust, trust_for_new_device
from .referral_contest_cache import get_cached_json, invalidate_referral_leaderboard_cache, referral_leaderboard_cache_key, set_cached_json
from .referral_contest_notifications import maybe_notify_referral_leaderboard_rank, notify_referrer_filleul_validated
from .models import (
    ReferralAttribution,
    ReferralEvent,
    ReferralLeaderboardEvent,
    ReferralPendingIntent,
    ReferrerReferralScore,
    UserReferralCode,
)

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 8

# Plafond journalier (par couple parrain / filleul) pour les micro-points « engagement » issus du concours fotos.
ENGAGEMENT_DAILY_CAP_PER_REFEREE_PAIR = 3.0

# Fenêtre « compte tout neuf » pour n’attribuer un parrain OAuth qu’à la création réelle (évite login ultérieur avec intent).
FRESH_USER_ATTRIBUTION_MAX_AGE_SEC = 900

# Pondération simple (extensible / admin plus tard). Les points forts vont au filleul validé.
POINTS_BY_EVENT: dict[str, float] = {
    # 1 filleul validé = 10 points au total.
    ReferralEvent.TYPE_SIGNUP_VALIDATED: 4.0,
    ReferralEvent.TYPE_REFERRAL_FINALIZED: 6.0,
    ReferralEvent.TYPE_FIRST_POST: 25.0,
    ReferralEvent.TYPE_FIRST_LOGIN: 5.0,
    ReferralEvent.TYPE_ENGAGEMENT: 10.0,
    ReferralEvent.TYPE_RETENTION: 15.0,
    ReferralEvent.TYPE_RETENTION_PROGRESS: 0.0,  # Calculé via paliers (bonus fidélité léger).
}


def referral_signup_reward_bundle_total() -> float:
    """Bloc unique crédité quand `_execute_referral_reward_grant` passe (somme signup + finalized)."""

    return float(
        POINTS_BY_EVENT.get(ReferralEvent.TYPE_SIGNUP_VALIDATED, 0.0)
        + POINTS_BY_EVENT.get(ReferralEvent.TYPE_REFERRAL_FINALIZED, 0.0)
    )


# Bonus fidélité progressif, volontairement modeste.
RETENTION_PROGRESS_MILESTONES: tuple[tuple[int, float], ...] = (
    (3, 1.0),
    (7, 1.5),
    (14, 2.0),
    (30, 3.0),
    (60, 4.0),
)

# Seuil d'affichage dans le leaderboard referral.
MIN_REFERRAL_LEADERBOARD_SCORE = 100.0


def _is_user_recently_created(user: User) -> bool:
    return (timezone.now() - user.date_joined).total_seconds() <= FRESH_USER_ATTRIBUTION_MAX_AGE_SEC


def normalize_referral_code(raw: str | None) -> str:
    if not raw:
        return ''
    s = str(raw).strip().upper()
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s[:16]


def generate_unique_referral_code() -> str:
    for _ in range(80):
        chunk = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not UserReferralCode.objects.filter(code=chunk).exists():
            return chunk
    raise RuntimeError('Impossible de générer un code referral unique')


def ensure_user_referral_code(user: User) -> UserReferralCode:
    existing = UserReferralCode.objects.filter(user=user).first()
    if existing:
        return existing
    with transaction.atomic():
        locked = User.objects.select_for_update().filter(pk=user.pk).first()
        if not locked:
            raise User.DoesNotExist
        again = UserReferralCode.objects.filter(user=user).first()
        if again:
            return again
        return UserReferralCode.objects.create(user=user, code=generate_unique_referral_code())


def _contest_period_for_now():
    return get_active_contest_settings()


def _extract_referral_code_from_request(request) -> str:
    if not request:
        return ''
    data = getattr(request, 'data', None)
    if isinstance(data, dict):
        v = data.get('referral_code') or data.get('ref')
        if v is not None and str(v).strip():
            return normalize_referral_code(str(v))
    try:
        g = request.GET.get('ref') or request.GET.get('referral_code')
        if g:
            return normalize_referral_code(str(g))
    except Exception:
        pass
    return ''


def _lookup_referrer_by_code(code: str) -> User | None:
    if not code:
        return None
    row = UserReferralCode.objects.filter(code=code).select_related('user').first()
    return row.user if row else None


def _latest_pending_intent(*, session_key: str = '', device_binding_id: str = '') -> ReferralPendingIntent | None:
    now = timezone.now()
    qs = ReferralPendingIntent.objects.filter(expires_at__gt=now).order_by('-created_at')
    if device_binding_id:
        hit = qs.filter(device_binding_id=device_binding_id).first()
        if hit:
            return hit
    if session_key:
        return qs.filter(session_key=session_key).first()
    return None


def store_referral_intent(
    *,
    code_raw: str,
    session_key: str = '',
    device_binding_id: str = '',
    utm: dict | None = None,
    ttl_days: int = 14,
) -> ReferralPendingIntent | None:
    code = normalize_referral_code(code_raw)
    if not code:
        return None
    if not session_key and not device_binding_id:
        return None
    expires = timezone.now() + timezone.timedelta(days=ttl_days)
    return ReferralPendingIntent.objects.create(
        session_key=session_key[:128] if session_key else '',
        device_binding_id=device_binding_id[:128] if device_binding_id else '',
        code_normalized=code,
        utm_json=utm or {},
        expires_at=expires,
    )


def _resolve_code_for_new_user(
    user: User,
    explicit_code: str | None,
    request,
    *,
    device_binding_header: str | None = None,
) -> tuple[str, str]:
    """
    Retourne (code, source) avec source dans ReferralAttribution.SOURCE_*.
    Priorité : code explicite > body/query (OAuth) > intent device (header) > intent session.
    """
    ex = normalize_referral_code(explicit_code or '')
    if ex:
        return ex, ReferralAttribution.SOURCE_SIGNUP_FIELD

    if request:
        from_req = _extract_referral_code_from_request(request)
        if from_req:
            return from_req, ReferralAttribution.SOURCE_OAUTH_COMPLETION

    device = (device_binding_header or '').strip()[:128]
    session_key = ''
    if request and hasattr(request, 'session') and request.session.session_key:
        session_key = request.session.session_key

    intent = _latest_pending_intent(session_key=session_key or '', device_binding_id=device)
    if intent:
        src = ReferralAttribution.SOURCE_DEEP_LINK if device else ReferralAttribution.SOURCE_LINK_QUERY
        return intent.code_normalized, src
    return '', ''


def record_referral_event(
    *,
    event_type: str,
    referee: User | None = None,
    referrer: User | None = None,
    metadata: dict | None = None,
    is_valid: bool = True,
    invalid_reason: str = '',
    score_delta: float = 0.0,
    trust_score: float = 1.0,
    contest=None,
) -> ReferralEvent:
    return ReferralEvent.objects.create(
        contest=contest,
        event_type=event_type,
        referee=referee,
        referrer=referrer,
        metadata=metadata or {},
        is_valid=is_valid,
        invalid_reason=invalid_reason,
        score_delta=score_delta,
        trust_score=trust_score,
    )


def _emit_referral_ws(*, contest, event_type: str, entity_id: int, payload: dict):
    row = ReferralLeaderboardEvent.objects.create(
        contest=contest,
        event_type=event_type,
        entity_id=entity_id,
        payload=payload,
    )
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    group_name = f'referral_{contest.contest_key.replace("-", "_")}'
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'referral.event',
            'payload': {
                'sequence': row.sequence,
                'event_type': row.event_type,
                'entity_id': row.entity_id,
                'payload': row.payload,
                'created_at': row.created_at.isoformat(),
            },
        },
    )


def _bump_referrer_score(*, contest, referrer: User, delta: float) -> ReferrerReferralScore | None:
    if delta == 0.0:
        return None
    with transaction.atomic():
        row, _ = ReferrerReferralScore.objects.select_for_update().get_or_create(
            contest=contest,
            referrer=referrer,
            defaults={'total_score': 0.0},
        )
        prev_rank = row.rank
        ReferrerReferralScore.objects.filter(pk=row.pk).update(total_score=F('total_score') + delta)
        row.refresh_from_db()
        higher = ReferrerReferralScore.objects.filter(contest=contest, total_score__gt=row.total_score).count()
        new_rank = higher + 1
        ReferrerReferralScore.objects.filter(pk=row.pk).update(previous_rank=prev_rank, rank=new_rank)
        row.refresh_from_db()
    invalidate_referral_leaderboard_cache(contest.id)
    _emit_referral_ws(
        contest=contest,
        event_type='referrer_rank_updated',
        entity_id=referrer.id,
        payload={
            'referrer_id': referrer.id,
            'username': referrer.username,
            'contest_key': contest.contest_key,
            'total_score': float(row.total_score or 0.0),
            'rank': row.rank,
            'previous_rank': prev_rank,
            'delta': delta,
        },
    )
    maybe_notify_referral_leaderboard_rank(
        recipient=referrer,
        contest_key=contest.contest_key,
        prev_rank=prev_rank if prev_rank > 0 else None,
        new_rank=row.rank,
        total_score=float(row.total_score or 0.0),
        contest_settings=contest,
    )
    return row


def assign_referrer_to_referee(
    *,
    referee: User,
    referrer: User,
    source: str,
    skip_email_pending: bool,
    trust: float = 1.0,
    request=None,
    signup_ip: str = '',
    signup_device_hash: str = '',
) -> ReferralAttribution | None:
    if is_self_referral(referee_id=referee.id, referrer_id=referrer.id):
        record_referral_event(
            event_type=ReferralEvent.TYPE_SIGNUP_STARTED,
            referee=referee,
            referrer=referrer,
            is_valid=False,
            invalid_reason='self_referral',
            metadata={'source': source},
        )
        return None

    contest = _contest_period_for_now()
    threshold = float(getattr(contest, 'trust_score_threshold', 0.4)) if contest else 0.4
    if should_reject_low_trust(trust=trust, threshold=threshold):
        record_referral_event(
            event_type=ReferralEvent.TYPE_SIGNUP_STARTED,
            referee=referee,
            referrer=referrer,
            is_valid=False,
            invalid_reason='trust_below_threshold',
            trust_score=trust,
            metadata={'source': source},
            contest=contest,
        )
        return None

    status = ReferralAttribution.STATUS_ACTIVE if skip_email_pending else ReferralAttribution.STATUS_PENDING_EMAIL
    try:
        with transaction.atomic():
            attr = ReferralAttribution.objects.create(
                referee=referee,
                referrer=referrer,
                status=status,
                source=source,
                activated_at=timezone.now() if status == ReferralAttribution.STATUS_ACTIVE else None,
                signup_ip=(signup_ip or '')[:64],
                signup_device_hash=(signup_device_hash or '')[:128],
            )
    except IntegrityError:
        return None

    record_referral_event(
        event_type=ReferralEvent.TYPE_SIGNUP_STARTED,
        referee=referee,
        referrer=referrer,
        is_valid=True,
        metadata={'source': source},
        contest=contest,
    )

    if status == ReferralAttribution.STATUS_ACTIVE:
        finalize_referral_attribution(attr, trust=trust)
    return attr


def consume_referral_for_new_user(
    referee: User,
    *,
    explicit_code: str | None,
    request,
    device_binding_header: str | None = None,
) -> ReferralAttribution | None:
    """Appelé après création User (email/password ou OAuth)."""
    if ReferralAttribution.objects.filter(referee=referee).exists():
        return ReferralAttribution.objects.filter(referee=referee).first()

    code, src = _resolve_code_for_new_user(
        referee,
        explicit_code,
        request,
        device_binding_header=device_binding_header,
    )
    if not code:
        return None

    referrer = _lookup_referrer_by_code(code)
    if not referrer or referrer.id == referee.id:
        return None

    trust = trust_for_new_device(referee.id)
    # Email/password : OTP requis avant points ; OAuth / email déjà vérifié : actif immédiat.
    skip_pending = _user_email_effectively_verified(referee)

    from .fraud_engine import precheck_new_referral, signup_fingerprint

    ok, reason = precheck_new_referral(referrer=referrer, referee=referee, request=request)
    if not ok:
        from .fraud_engine import log_audit

        log_audit(action='referral_precheck_failed', user=referee, metadata={'reason': reason, 'referrer_id': referrer.id}, request=request)
        return None

    sip, sdev = signup_fingerprint(request) if request else ('', '')
    return assign_referrer_to_referee(
        referee=referee,
        referrer=referrer,
        source=src,
        skip_email_pending=skip_pending,
        trust=trust,
        request=request,
        signup_ip=sip or '',
        signup_device_hash=sdev or '',
    )


def _user_email_effectively_verified(user: User) -> bool:
    from allauth.account.models import EmailAddress

    if EmailAddress.objects.filter(user=user, verified=True).exists():
        return True
    return False


def finalize_referral_on_email_verified(user: User) -> None:
    attr = ReferralAttribution.objects.filter(
        referee=user,
        status=ReferralAttribution.STATUS_PENDING_EMAIL,
    ).first()
    if not attr:
        return
    finalize_referral_attribution(attr, trust=trust_for_new_device(user.id))


def try_complete_referral_rewards(attr: ReferralAttribution) -> str:
    """Tente de créditer le parrain si tous les garde-fous anti-fraude sont passés."""
    from . import fraud_engine

    attr = ReferralAttribution.objects.select_related('referee', 'referrer').filter(pk=attr.pk).first()
    if not attr or attr.rewards_granted_at:
        return 'skip'
    ok, reason = fraud_engine.evaluate_referral_reward_eligibility(attr)
    if not ok:
        return reason
    contest = _contest_period_for_now()
    trust = trust_for_new_device(attr.referee_id)
    _execute_referral_reward_grant(attr, trust=trust, contest=contest)
    return 'granted'


def _execute_referral_reward_grant(attr: ReferralAttribution, *, trust: float, contest) -> None:
    """Crédit unique des points signup + finalisation (après validation différée)."""
    pts_final = POINTS_BY_EVENT.get(ReferralEvent.TYPE_REFERRAL_FINALIZED, 0.0)
    pts_val = POINTS_BY_EVENT.get(ReferralEvent.TYPE_SIGNUP_VALIDATED, 0.0)
    total_delta = pts_val + pts_final
    from .fraud_engine import log_audit
    from .referral_contest_notifications import notify_referrer_reward_unlocked

    with transaction.atomic():
        row = ReferralAttribution.objects.select_for_update().filter(pk=attr.pk, rewards_granted_at__isnull=True).first()
        if not row:
            return
        record_referral_event(
            event_type=ReferralEvent.TYPE_REFERRAL_FINALIZED,
            referee=row.referee,
            referrer=row.referrer,
            is_valid=True,
            score_delta=total_delta,
            trust_score=trust,
            contest=contest,
            metadata={'deferred_grant': True},
        )
        record_referral_event(
            event_type=ReferralEvent.TYPE_REWARD_GRANTED,
            referee=row.referee,
            referrer=row.referrer,
            is_valid=True,
            score_delta=0.0,
            trust_score=trust,
            contest=contest,
            metadata={'points': total_delta},
        )
        ReferralAttribution.objects.filter(pk=row.pk).update(rewards_granted_at=timezone.now())
        if contest:
            _bump_referrer_score(contest=contest, referrer=row.referrer, delta=total_delta)

    log_audit(action='referral_rewards_granted', attribution=attr, user=attr.referee, metadata={'trust': trust})
    notify_referrer_reward_unlocked(
        referrer=attr.referrer,
        contest_key=getattr(contest, 'contest_key', '') if contest else '',
        message_fr=f'Récompense parrainage débloquée pour {attr.referee.username} (+{total_delta:.0f} pts).',
    )


def finalize_referral_attribution(attr: ReferralAttribution, *, trust: float = 1.0) -> None:
    if attr.rewards_granted_at:
        return

    contest = _contest_period_for_now()
    threshold = float(getattr(contest, 'trust_score_threshold', 0.4)) if contest else 0.4
    if should_reject_low_trust(trust=trust, threshold=threshold):
        ReferralAttribution.objects.filter(pk=attr.pk).update(status=ReferralAttribution.STATUS_REVOKED)
        record_referral_event(
            event_type=ReferralEvent.TYPE_REFERRAL_FINALIZED,
            referee=attr.referee,
            referrer=attr.referrer,
            is_valid=False,
            invalid_reason='trust_below_threshold_on_finalize',
            contest=contest,
        )
        return

    now = timezone.now()
    with transaction.atomic():
        locked = ReferralAttribution.objects.select_for_update().filter(pk=attr.pk).first()
        if not locked:
            return
        if locked.status == ReferralAttribution.STATUS_PENDING_EMAIL:
            locked.status = ReferralAttribution.STATUS_ACTIVE
            if not locked.activated_at:
                locked.activated_at = now
        if not locked.email_verified_at:
            locked.email_verified_at = now
        locked.save(update_fields=['status', 'activated_at', 'email_verified_at'])
    attr.refresh_from_db()

    record_referral_event(
        event_type=ReferralEvent.TYPE_SIGNUP_VALIDATED,
        referee=attr.referee,
        referrer=attr.referrer,
        is_valid=True,
        score_delta=0.0,
        trust_score=trust,
        contest=contest,
        metadata={'phase': 'email_verified_no_points'},
    )

    referral_settings = get_referral_settings_for_contest(contest)
    defer = bool(referral_settings and getattr(referral_settings, 'defer_rewards', getattr(referral_settings, 'referral_defer_rewards', True)))
    if defer:
        record_referral_event(
            event_type=ReferralEvent.TYPE_REWARD_DEFERRED,
            referee=attr.referee,
            referrer=attr.referrer,
            is_valid=True,
            score_delta=0.0,
            trust_score=trust,
            contest=contest,
            metadata={'from': 'finalize_referral_attribution'},
        )
        from .referral_contest_notifications import notify_referrer_reward_unlocked

        notify_referrer_reward_unlocked(
            referrer=attr.referrer,
            contest_key=getattr(contest, 'contest_key', '') if contest else '',
            message_fr=f'{attr.referee.username} progresse bien ; vos points parrainage seront crédités dès validation des règles du concours.',
        )
        try_complete_referral_rewards(attr)
        return

    try_complete_referral_rewards(attr)


def assign_referrer_from_registration_context(user: User, request, sociallogin=None) -> None:
    """Hook allauth après création/liaison compte social."""
    if not _is_user_recently_created(user):
        return
    device = ''
    if request:
        device = (request.META.get('HTTP_X_FOTOCE_DEVICE_BINDING') or '').strip()[:128]
    code = _extract_referral_code_from_request(request)
    consume_referral_for_new_user(user, explicit_code=code or None, request=request, device_binding_header=device or None)


def try_apply_onboarding_referral(
    user: User,
    *,
    referral_code_optional: str | None,
    request,
    device_binding_header: str | None = None,
) -> dict[str, Any]:
    """
    Modal OAuth : code optionnel seulement si aucune attribution existante / verrouillée par intent.
    """
    existing = ReferralAttribution.objects.filter(referee=user).first()
    if existing:
        if existing.status in (
            ReferralAttribution.STATUS_ACTIVE,
            ReferralAttribution.STATUS_PENDING_EMAIL,
        ):
            return {'applied': False, 'reason': 'already_has_referrer', 'locked': True}
        if existing.status == ReferralAttribution.STATUS_REVOKED:
            existing.delete()

    code_modal = normalize_referral_code(referral_code_optional or '')
    code_intent, _src = _resolve_code_for_new_user(user, None, request, device_binding_header=device_binding_header)

    if code_intent and code_modal and normalize_referral_code(code_intent) != normalize_referral_code(code_modal):
        return {'applied': False, 'reason': 'conflict_with_tracked_link', 'locked': True}

    final_code = code_intent or code_modal
    if not final_code:
        return {'applied': False, 'reason': 'no_code'}

    referrer = _lookup_referrer_by_code(final_code)
    if not referrer or referrer.id == user.id:
        return {'applied': False, 'reason': 'invalid_code'}

    trust = trust_for_new_device(user.id)
    src = ReferralAttribution.SOURCE_ONBOARDING_MODAL if code_modal and not code_intent else ReferralAttribution.SOURCE_OAUTH_COMPLETION
    from .fraud_engine import precheck_new_referral, signup_fingerprint

    ok, reason = precheck_new_referral(referrer=referrer, referee=user, request=request)
    if not ok:
        return {'applied': False, 'reason': reason}
    sip, sdev = signup_fingerprint(request) if request else ('', '')
    attr = assign_referrer_to_referee(
        referee=user,
        referrer=referrer,
        source=src,
        skip_email_pending=_user_email_effectively_verified(user),
        trust=trust,
        request=request,
        signup_ip=sip or '',
        signup_device_hash=sdev or '',
    )
    return {'applied': bool(attr), 'referrer_id': referrer.id if attr else None}


def award_engagement_from_referee_to_referrer(
    *,
    referee,
    contest,
    trust_score: float,
    foto_id: int | None = None,
) -> None:
    """Micro-points pour activité d’un filleul (interaction concours fotos valide sur autrui)."""
    from django.core.cache import cache

    if not contest:
        return
    attr = (
        ReferralAttribution.objects.filter(referee_id=referee.id, status=ReferralAttribution.STATUS_ACTIVE)
        .select_related('referrer')
        .first()
    )
    if not attr:
        return
    try_complete_referral_rewards(attr)
    attr.refresh_from_db()
    if not attr.rewards_granted_at:
        return
    day = timezone.now().date().isoformat()
    key = f'refl_engsum:{contest.id}:{attr.referrer_id}:{referee.id}:{day}'
    prev = float(cache.get(key) or 0.0)
    if prev >= ENGAGEMENT_DAILY_CAP_PER_REFEREE_PAIR:
        return
    base = POINTS_BY_EVENT.get(ReferralEvent.TYPE_ENGAGEMENT, 0.0) * max(0.2, min(1.0, float(trust_score))) * 0.12
    delta = min(base, ENGAGEMENT_DAILY_CAP_PER_REFEREE_PAIR - prev)
    if delta <= 0.001:
        return
    record_referral_event(
        event_type=ReferralEvent.TYPE_ENGAGEMENT,
        referee=referee,
        referrer=attr.referrer,
        is_valid=True,
        score_delta=delta,
        trust_score=float(trust_score),
        contest=contest,
        metadata={'foto_id': foto_id} if foto_id else {},
    )
    _bump_referrer_score(contest=contest, referrer=attr.referrer, delta=delta)
    cache.set(key, prev + delta, timeout=86400)


def on_referee_first_login(user: User) -> None:
    if ReferralEvent.objects.filter(
        referee=user,
        event_type=ReferralEvent.TYPE_FIRST_LOGIN,
        is_valid=True,
    ).exists():
        return
    attr = ReferralAttribution.objects.filter(
        referee=user,
        status=ReferralAttribution.STATUS_ACTIVE,
    ).select_related('referrer').first()
    if not attr:
        return
    try_complete_referral_rewards(attr)
    attr.refresh_from_db()
    if not attr.rewards_granted_at:
        return
    contest = _contest_period_for_now()
    delta = POINTS_BY_EVENT.get(ReferralEvent.TYPE_FIRST_LOGIN, 0.0)
    if delta <= 0:
        return
    record_referral_event(
        event_type=ReferralEvent.TYPE_FIRST_LOGIN,
        referee=user,
        referrer=attr.referrer,
        is_valid=True,
        score_delta=delta,
        contest=contest,
    )
    if contest:
        _bump_referrer_score(contest=contest, referrer=attr.referrer, delta=delta)
    _grant_retention_progress_bonus_if_eligible(attr)


def grant_retention_bonus_if_eligible(attr: ReferralAttribution) -> bool:
    """Rétention : filleul toujours actif et reconnecté après la fenêtre de grâce (7 j)."""
    if attr.status != ReferralAttribution.STATUS_ACTIVE or not attr.activated_at:
        return False
    try_complete_referral_rewards(attr)
    attr.refresh_from_db()
    if not attr.rewards_granted_at:
        return False
    now = timezone.now()
    if attr.activated_at > now - timezone.timedelta(days=7):
        return False
    if ReferralEvent.objects.filter(
        referee_id=attr.referee_id,
        referrer_id=attr.referrer_id,
        event_type=ReferralEvent.TYPE_RETENTION,
        is_valid=True,
    ).exists():
        return False
    last = attr.referee.last_login
    if not last or last < attr.activated_at + timezone.timedelta(days=7):
        return False
    contest = _contest_period_for_now()
    delta = POINTS_BY_EVENT.get(ReferralEvent.TYPE_RETENTION, 0.0)
    if delta <= 0:
        return False
    record_referral_event(
        event_type=ReferralEvent.TYPE_RETENTION,
        referee=attr.referee,
        referrer=attr.referrer,
        is_valid=True,
        score_delta=delta,
        contest=contest,
    )
    if contest:
        _bump_referrer_score(contest=contest, referrer=attr.referrer, delta=delta)
    _grant_retention_progress_bonus_if_eligible(attr)
    return True


def _grant_retention_progress_bonus_if_eligible(attr: ReferralAttribution) -> float:
    """
    Petit bonus progressif quand le filleul reste actif.
    Chaque palier est crédité une seule fois.
    """
    if attr.status != ReferralAttribution.STATUS_ACTIVE or not attr.activated_at:
        return 0.0
    if not attr.rewards_granted_at:
        return 0.0

    contest = _contest_period_for_now()
    if not contest:
        return 0.0

    active_days = max(0, (timezone.now() - attr.activated_at).days)
    if active_days <= 0:
        return 0.0

    total_delta = 0.0
    for min_days, delta in RETENTION_PROGRESS_MILESTONES:
        if active_days < min_days:
            continue
        already_awarded = ReferralEvent.objects.filter(
            referee_id=attr.referee_id,
            referrer_id=attr.referrer_id,
            event_type=ReferralEvent.TYPE_RETENTION_PROGRESS,
            is_valid=True,
            metadata__milestone_days=min_days,
        ).exists()
        if already_awarded:
            continue

        record_referral_event(
            event_type=ReferralEvent.TYPE_RETENTION_PROGRESS,
            referee=attr.referee,
            referrer=attr.referrer,
            is_valid=True,
            score_delta=delta,
            contest=contest,
            metadata={'milestone_days': min_days, 'active_days': active_days},
        )
        total_delta += delta

    if total_delta > 0:
        _bump_referrer_score(contest=contest, referrer=attr.referrer, delta=total_delta)
    return total_delta


def on_first_foto_created(user: User) -> None:
    attr = ReferralAttribution.objects.filter(referee=user, status=ReferralAttribution.STATUS_ACTIVE).first()
    if not attr:
        return
    try_complete_referral_rewards(attr)
    attr.refresh_from_db()
    if not attr.rewards_granted_at:
        return
    contest = _contest_period_for_now()
    delta = POINTS_BY_EVENT.get(ReferralEvent.TYPE_FIRST_POST, 0.0)
    record_referral_event(
        event_type=ReferralEvent.TYPE_FIRST_POST,
        referee=user,
        referrer=attr.referrer,
        is_valid=True,
        score_delta=delta,
        contest=contest,
    )
    if contest and delta:
        _bump_referrer_score(contest=contest, referrer=attr.referrer, delta=delta)
    _grant_retention_progress_bonus_if_eligible(attr)


def build_public_resolve_payload(*, code: str) -> dict[str, Any] | None:
    code_n = normalize_referral_code(code)
    if not code_n:
        return None
    row = UserReferralCode.objects.filter(code=code_n).select_related('user', 'user__profile').first()
    if not row:
        return None
    display = row.user.profile.display_name or row.user.username
    return {
        'code': row.code,
        'inviter_display_name': display[:80],
        'valid': True,
    }


def build_me_referral_payload(user: User, request) -> dict[str, Any]:
    from django.conf import settings as dj_settings

    identity = ensure_user_referral_code(user)
    base = getattr(dj_settings, 'FRONTEND_URL', 'http://localhost:5174').rstrip('/')
    scheme = getattr(dj_settings, 'REFERRAL_DEEP_LINK_SCHEME', 'fotoce')
    attr = ReferralAttribution.objects.filter(referee=user).select_related('referrer').first()
    received = None
    if attr:
        received = {
            'referrer_username': attr.referrer.username,
            'status': attr.status,
        }
    return {
        'my_code': identity.code,
        'link_web': f'{base}/register?ref={identity.code}',
        'link_deep': f'{scheme}://invite?ref={identity.code}',
        'link_universal': f'{base}/r/{identity.code}',
        'received': received,
    }


def referral_leaderboard_rows(*, contest_id: int | None = None, limit: int = 50):
    contest = None
    if contest_id:
        from contests.models import ContestSettings

        contest = ContestSettings.objects.filter(pk=contest_id).first()
    if not contest:
        contest = _contest_period_for_now()
    if not contest:
        return []
    rows = (
        ReferrerReferralScore.objects.filter(contest=contest, total_score__gte=MIN_REFERRAL_LEADERBOARD_SCORE)
        .select_related('referrer')
        .order_by('rank', '-total_score')[:limit]
    )
    out = []
    for r in rows:
        out.append(
            {
                'rank': r.rank,
                'referrer_id': r.referrer_id,
                'username': r.referrer.username,
                'total_score': float(r.total_score or 0.0),
            },
        )
    return out


def build_referral_leaderboard_http_payload(request, *, contest_id: int | None, limit: int) -> dict[str, Any]:
    from contests.models import ContestSettings

    contest = None
    if contest_id:
        contest = ContestSettings.objects.filter(pk=contest_id).first()
    if not contest:
        contest = _contest_period_for_now()
    if not contest:
        return {'contest_key': None, 'results': [], 'viewer': None, 'refresh_interval': 3}

    contest_cap = max(25, min(max(int(getattr(contest, 'max_winners', 3) or 3) * 40, 100), 200))
    limit = min(max(limit, 1), contest_cap)
    cache_key = referral_leaderboard_cache_key(contest_id=contest.id, limit=limit)
    cached = get_cached_json(cache_key)
    if isinstance(cached, dict):
        return cached

    ordered_full = list(
        ReferrerReferralScore.objects.filter(contest=contest, total_score__gte=MIN_REFERRAL_LEADERBOARD_SCORE)
        .select_related('referrer')
        .order_by('-total_score', 'referrer_id'),
    )
    rank_map = {row.referrer_id: idx + 1 for idx, row in enumerate(ordered_full)}
    slice_rows = ordered_full[:limit]
    results = [
        {
            'rank': rank_map.get(r.referrer_id, r.rank or 0),
            'referrer_id': r.referrer_id,
            'username': r.referrer.username,
            'total_score': float(r.total_score or 0.0),
            'previous_rank': r.previous_rank,
        }
        for r in slice_rows
    ]
    viewer_payload = None
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        uid = user.pk
        viewer_rank = rank_map.get(uid)
        viewer_row = next((x for x in ordered_full if x.referrer_id == uid), None)
        if viewer_row is not None and viewer_rank is not None:
            viewer_payload = {
                'ranked': True,
                'rank': viewer_rank,
                'in_displayed_top': viewer_rank <= limit,
                'row': {
                    'rank': viewer_rank,
                    'referrer_id': viewer_row.referrer_id,
                    'username': viewer_row.referrer.username,
                    'total_score': float(viewer_row.total_score or 0.0),
                    'previous_rank': viewer_row.previous_rank,
                },
            }
        else:
            viewer_payload = {'ranked': False, 'rank': None, 'in_displayed_top': False, 'row': None}

    refresh = max(1, min(300, int(getattr(contest, 'leaderboard_refresh_interval', 3) or 3)))
    payload = {
        'contest_key': contest.contest_key,
        'contest_id': contest.id,
        'results': results,
        'viewer': viewer_payload,
        'refresh_interval': refresh,
    }
    set_cached_json(cache_key, payload)
    return payload
