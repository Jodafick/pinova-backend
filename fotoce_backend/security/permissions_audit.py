"""Audit des permissions DRF — repère AllowAny sans throttling."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.views import APIView


# Vues documentées : AllowAny légitime avec throttle hors DEFAULT_THROTTLE_CLASSES.
# Clé = nom de la vue DRF ; valeur = libellé throttle effectif (audit statique).
AUDIT_THROTTLE_OVERRIDES: dict[str, str] = {
    'VerifyOTPView': 'OtpVerifyIPThrottle + django-ratelimit (otp_verify)',
    'ResendOTPView': 'OtpResendEmailThrottle + django-ratelimit (otp_resend)',
    'SubscriptionWebhookView': 'WebhookIPThrottle + django-ratelimit (fedapay_webhook)',
}


@dataclass(frozen=True)
class PublicEndpointFinding:
    route: str
    view_name: str
    permission_classes: tuple[str, ...]
    throttle_classes: tuple[str, ...]
    uses_default_permissions: bool
    uses_default_throttles: bool


def _import_drf_class(path: str):
    module_path, class_name = path.rsplit('.', 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def _permission_label(perm) -> str:
    if isinstance(perm, type):
        return perm.__name__
    return perm.__class__.__name__


def _is_allow_any(perm) -> bool:
    if perm is AllowAny:
        return True
    if isinstance(perm, type) and issubclass(perm, AllowAny):
        return True
    if isinstance(perm, BasePermission) and perm.__class__ is AllowAny:
        return True
    return False


def _resolve_permission_classes(view) -> tuple[list, bool]:
    perms = getattr(view, 'permission_classes', None)
    if perms is None:
        default_paths = settings.REST_FRAMEWORK.get('DEFAULT_PERMISSION_CLASSES', [])
        return [_import_drf_class(p) for p in default_paths], True
    resolved = []
    for item in perms:
        resolved.append(item() if isinstance(item, type) and issubclass(item, BasePermission) else item)
    return resolved, False


def _resolve_throttle_classes(view) -> tuple[list, bool]:
    throttles = getattr(view, 'throttle_classes', None)
    if throttles is None:
        default_paths = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_CLASSES', [])
        return [_import_drf_class(p) for p in default_paths], True
    return list(throttles), False


def view_uses_allow_any(view) -> bool:
    perms, _uses_default = _resolve_permission_classes(view)
    return any(_is_allow_any(p) for p in perms)


def _unwrap_view(callback):
    view = callback
    while hasattr(view, 'cls'):
        view = view.cls
    while hasattr(view, 'view_class'):
        view = view.view_class
    if hasattr(view, 'view'):
        view = view.view
    return view


def _iter_patterns(patterns, prefix=''):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            nested = prefix + str(pattern.pattern)
            yield from _iter_patterns(pattern.url_patterns, nested)
            continue
        if isinstance(pattern, URLPattern):
            route = prefix + str(pattern.pattern)
            yield route, pattern.callback, pattern.name or ''


def collect_public_endpoints(*, resolver=None) -> list[PublicEndpointFinding]:
    resolver = resolver or get_resolver()
    findings: list[PublicEndpointFinding] = []

    for route, callback, _name in _iter_patterns(resolver.url_patterns):
        if not route.startswith('api/'):
            continue
        view = _unwrap_view(callback)
        if not isinstance(view, type) or not issubclass(view, APIView):
            continue
        if not view_uses_allow_any(view):
            continue
        perms, uses_default_perms = _resolve_permission_classes(view)
        throttles, uses_default_throttles = _resolve_throttle_classes(view)
        findings.append(
            PublicEndpointFinding(
                route=f'/{route}',
                view_name=view.__name__,
                permission_classes=tuple(_permission_label(p) for p in perms),
                throttle_classes=tuple(_permission_label(t) for t in throttles),
                uses_default_permissions=uses_default_perms,
                uses_default_throttles=uses_default_throttles,
            ),
        )
    return sorted(findings, key=lambda row: row.route)


def collect_allow_any_missing_throttle(*, resolver=None) -> list[PublicEndpointFinding]:
    rows = []
    for row in collect_public_endpoints(resolver=resolver):
        if row.throttle_classes:
            continue
        if row.view_name in AUDIT_THROTTLE_OVERRIDES:
            continue
        rows.append(row)
    return rows
