"""Throttles dédiés aux endpoints OTP."""

from __future__ import annotations

from pinova_backend.security.throttling import IPThrottleMixin, _clean_ident
from rest_framework.throttling import SimpleRateThrottle

from accounts.otp_security import normalize_otp_email


class OtpVerifyIPThrottle(SimpleRateThrottle, IPThrottleMixin):
    scope = 'otp_verify'

    def get_cache_key(self, request, view):
        return IPThrottleMixin.get_cache_key(self, request, view)


class OtpResendEmailThrottle(SimpleRateThrottle):
    scope = 'otp_resend'

    def get_cache_key(self, request, view):
        email = normalize_otp_email(getattr(request, 'data', {}).get('email'))
        if not email:
            return None
        ident = _clean_ident(email)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
