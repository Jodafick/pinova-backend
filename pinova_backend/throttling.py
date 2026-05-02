"""
Quota API : limite les requêtes par IP (anonymes) et par utilisateur authentifié.

Les préfixes sont surchargées via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] dans settings.py
(API_THROTTLE_* environnement). Respecte X-Forwarded-For lorsque placé derrière un proxy.

Les webhooks paiement externes ne passent généralement pas par ces quotas (AllowAny mais
vous pouvez exclure des chemins avec un throttle personnalisé ou une classe dédiée).
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


def client_ip_from_request(request) -> str:
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip() or 'unknown'
    addr = request.META.get('REMOTE_ADDR') or ''
    return addr.strip() or 'unknown'


def _clean_ident(ident: str) -> str:
    """Cache keys : éviter ':' et espaces (Memcached)."""
    return ''.join(c for c in str(ident) if c.isalnum() or c in '._-')


class IPThrottleMixin:
    """Utilise la première IP cliente (Forwarded-For prioritaire)."""

    def get_cache_key(self, request, view):
        ident = _clean_ident(client_ip_from_request(request))
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AnonIPRateThrottle(SimpleRateThrottle, IPThrottleMixin):
    """Requêtes non authentifiées : fenêtre unique par scopes `anon_burst` puis `anon_sustained`."""

    scope = 'anon_burst'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return IPThrottleMixin.get_cache_key(self, request, view)


class AuthenticatedUserRateThrottle(SimpleRateThrottle):
    """Compteur par utilisateur (pk). Pas de throttle pour anon (géré à part)."""

    scope = 'user_burst'

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        ident = _clean_ident(user.pk)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AuthenticatedUserSustainedThrottle(SimpleRateThrottle):
    scope = 'user_sustained'

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        ident = _clean_ident(user.pk)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AnonIPSustainedThrottle(SimpleRateThrottle, IPThrottleMixin):
    scope = 'anon_sustained'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return IPThrottleMixin.get_cache_key(self, request, view)
