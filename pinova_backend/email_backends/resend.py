import logging

import resend
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMultiAlternatives

from pinova_backend.security.resilience import ExternalRetryableError, external_call

logger = logging.getLogger(__name__)


class ResendBackend(BaseEmailBackend):
    """
    Envoie les messages Django via l'API Resend (sdk ``import resend``).
    Compatible avec ``send_mail`` et les e-mails texte/HTML existants.
    Retry 2× (3 tentatives) sur erreurs transitoires ; fallback SMTP inchangé côté settings.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = (getattr(settings, 'RESEND_API_KEY', None) or '').strip()
        if not api_key:
            msg = 'RESEND_API_KEY est requis pour le backend Resend.'
            logger.error(msg)
            if not self.fail_silently:
                raise ValueError(msg)
            return 0

        resend.api_key = api_key
        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
                logger.exception('Échec envoi Resend (sujet=%r)', message.subject)
        return sent

    def _send_one(self, message):
        params = self._build_params(message)

        def _do():
            try:
                resend.Emails.send(params)
            except Exception as exc:
                raise ExternalRetryableError(str(exc)) from exc

        external_call(
            service='resend',
            operation='emails.send',
            fn=_do,
            max_attempts=3,
        )

    def _build_params(self, message):
        from_email = message.from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not from_email:
            raise ValueError('Adresse expéditeur manquante (from_email / DEFAULT_FROM_EMAIL).')

        to = list(message.to or [])
        cc = list(message.cc or [])
        bcc = list(message.bcc or [])
        if not to and not cc and not bcc:
            raise ValueError('Aucun destinataire (to/cc/bcc).')

        params = {
            'from': from_email,
            'to': to,
            'subject': message.subject or '',
        }
        if cc:
            params['cc'] = cc
        if bcc:
            params['bcc'] = bcc

        html_body = None
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == 'text/html':
                    html_body = content
                    break

        body = message.body or ''
        if html_body:
            params['html'] = html_body
            if body.strip():
                params['text'] = body
        else:
            params['text'] = body

        reply_to = getattr(message, 'reply_to', None) or []
        if reply_to:
            params['reply_to'] = list(reply_to)
        return params
