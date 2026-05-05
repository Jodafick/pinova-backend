"""
Envoi d’e-mails avec repli entre le backend configuré (Resend ou SMTP) et l’autre canal si disponible.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import get_connection, send_mail

logger = logging.getLogger(__name__)

EMAIL_DELIVERY_ERROR_CODE = 'email_delivery_unavailable'

# Message lisible côté API (les clients préfèrent les clés i18n quand elles existent).
EMAIL_DELIVERY_USER_MESSAGE = (
    'Nous ne pouvons pas vous envoyer le code par e-mail pour le moment. '
    'Vous pouvez vous connecter ou créer un compte avec Google à la place, sans attendre de code.'
)

RESEND_BACKEND = 'pinova_backend.email_backends.resend.ResendBackend'
SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'


class EmailDeliveryUnavailable(Exception):
    """Levié lorsque tous les canaux d’envoi disponibles ont échoué."""

    code = EMAIL_DELIVERY_ERROR_CODE


def _resend_ready() -> bool:
    return bool((getattr(settings, 'RESEND_API_KEY', None) or '').strip())


def _smtp_ready() -> bool:
    user = (getattr(settings, 'EMAIL_HOST_USER', None) or '').strip()
    password = (getattr(settings, 'EMAIL_HOST_PASSWORD', None) or '').strip()
    return bool(user and password)


def _mail_backend_chain() -> list[str]:
    primary = (getattr(settings, 'EMAIL_BACKEND', None) or '').strip() or SMTP_BACKEND
    candidates: list[str] = [primary]
    if _resend_ready() and RESEND_BACKEND != primary:
        candidates.append(RESEND_BACKEND)
    if _smtp_ready() and SMTP_BACKEND != primary:
        candidates.append(SMTP_BACKEND)
    ordered: list[str] = []
    for b in candidates:
        if b and b not in ordered:
            ordered.append(b)
    return ordered


def send_pinova_mail(
    subject: str,
    message: str,
    from_email: str | None,
    recipient_list: list[str],
    *,
    fail_silently: bool = False,
) -> None:
    """
    Essaie le backend principal puis l’autre (Resend ↔ SMTP) si configuré.
    Lève ``EmailDeliveryUnavailable`` si tout échoue (ou ``fail_silently`` et aucun envoi).
    """
    if not recipient_list:
        raise EmailDeliveryUnavailable()

    backends = _mail_backend_chain()
    last_exc: Optional[BaseException] = None

    for backend in backends:
        try:
            connection = get_connection(backend=backend, fail_silently=False)
            send_mail(
                subject,
                message,
                from_email,
                recipient_list,
                fail_silently=False,
                connection=connection,
            )
            return
        except Exception as exc:
            last_exc = exc
            logger.warning('Échec envoi e-mail (backend=%s)', backend, exc_info=True)

    if fail_silently:
        return

    raise EmailDeliveryUnavailable() from last_exc
