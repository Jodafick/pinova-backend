"""Limites anti brute-force pour vérification / renvoi OTP."""

from __future__ import annotations

import time

from django.core.cache import cache
from django.utils import timezone

MAX_VERIFY_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
RESEND_COOLDOWN_SECONDS = 60
MAX_RESENDS_PER_HOUR = 5
RESEND_HOUR_WINDOW = 3600

OTP_GENERIC_INVALID_FR = 'Code invalide ou expiré.'
OTP_GENERIC_RESEND_OK_FR = (
    'Si un compte existe avec cet e-mail et nécessite une validation, un code a été envoyé.'
)

CODE_OTP_INVALID = 'fotoce_otp_invalid'
CODE_OTP_LOCKED = 'fotoce_otp_locked'
CODE_OTP_RESEND_COOLDOWN = 'fotoce_otp_resend_cooldown'
CODE_OTP_RESEND_LIMIT = 'fotoce_otp_resend_limit'

_VERIFY_ATTEMPTS_PREFIX = 'fotoce:otp:verify:'
_LOCKOUT_PREFIX = 'fotoce:otp:lockout:'
_RESEND_COOLDOWN_PREFIX = 'fotoce:otp:resend_cd:'
_RESEND_HOUR_PREFIX = 'fotoce:otp:resend_h:'


def normalize_otp_email(email: str | None) -> str:
    return (email or '').strip().lower()


def _verify_attempts_key(email: str) -> str:
    return f'{_VERIFY_ATTEMPTS_PREFIX}{normalize_otp_email(email)}'


def _lockout_key(email: str) -> str:
    return f'{_LOCKOUT_PREFIX}{normalize_otp_email(email)}'


def _resend_cooldown_key(email: str) -> str:
    return f'{_RESEND_COOLDOWN_PREFIX}{normalize_otp_email(email)}'


def _resend_hour_key(email: str) -> str:
    return f'{_RESEND_HOUR_PREFIX}{normalize_otp_email(email)}'


def _cache_get(key: str, default=None):
    try:
        return cache.get(key, default)
    except Exception:
        return default


def _cache_set(key: str, value, *, timeout: int | None = None) -> None:
    try:
        cache.set(key, value, timeout=timeout)
    except Exception:
        pass


def _cache_delete(key: str) -> None:
    try:
        cache.delete(key)
    except Exception:
        pass


def _cache_incr(key: str, *, timeout: int) -> int:
    try:
        return cache.incr(key)
    except ValueError:
        _cache_set(key, 1, timeout=timeout)
        return 1
    except Exception:
        return 1


def lockout_status(email: str) -> tuple[bool, int]:
    """Retourne (verrouillé, secondes restantes)."""
    raw = _cache_get(_lockout_key(email))
    if raw is None:
        return False, 0
    try:
        expires_at = float(raw)
    except (TypeError, ValueError):
        _cache_delete(_lockout_key(email))
        return False, 0
    remaining = int(expires_at - time.time())
    if remaining <= 0:
        _cache_delete(_lockout_key(email))
        _cache_delete(_verify_attempts_key(email))
        return False, 0
    return True, remaining


def _set_lockout(email: str) -> None:
    _cache_set(_lockout_key(email), time.time() + LOCKOUT_SECONDS, timeout=LOCKOUT_SECONDS)


def record_failed_verify(email: str) -> int:
    key = _verify_attempts_key(email)
    count = _cache_incr(key, timeout=LOCKOUT_SECONDS)
    if count >= MAX_VERIFY_ATTEMPTS:
        _set_lockout(email)
    return count


def attempts_remaining(email: str) -> int:
    locked, _ = lockout_status(email)
    if locked:
        return 0
    used = _cache_get(_verify_attempts_key(email), 0) or 0
    return max(0, MAX_VERIFY_ATTEMPTS - int(used))


def clear_verify_security(email: str) -> None:
    _cache_delete(_verify_attempts_key(email))
    _cache_delete(_lockout_key(email))


def register_verify_failure(email: str) -> dict:
    record_failed_verify(email)
    locked, retry_after = lockout_status(email)
    payload = {
        'error': OTP_GENERIC_INVALID_FR,
        'code': CODE_OTP_LOCKED if locked else CODE_OTP_INVALID,
        'attempts_remaining': attempts_remaining(email),
    }
    if locked:
        payload['retry_after_seconds'] = retry_after
        payload['locked_until'] = (
            timezone.now() + timezone.timedelta(seconds=retry_after)
        ).isoformat()
    return payload


def resend_cooldown_remaining(email: str) -> int:
    sent_at = _cache_get(_resend_cooldown_key(email))
    if sent_at is None:
        return 0
    try:
        elapsed = time.time() - float(sent_at)
    except (TypeError, ValueError):
        _cache_delete(_resend_cooldown_key(email))
        return 0
    return max(0, RESEND_COOLDOWN_SECONDS - int(elapsed))


def resend_hourly_count(email: str) -> int:
    return int(_cache_get(_resend_hour_key(email), 0) or 0)


def mark_resend_sent(email: str) -> None:
    _cache_set(_resend_cooldown_key(email), time.time(), timeout=RESEND_COOLDOWN_SECONDS)


def increment_resend_hourly(email: str) -> int:
    return _cache_incr(_resend_hour_key(email), timeout=RESEND_HOUR_WINDOW)
