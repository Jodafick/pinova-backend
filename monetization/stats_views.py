"""Stats publiques monétisation + email récap paiement pending."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .social_proof import total_boosts_activated

logger = logging.getLogger(__name__)


class PublicMonetizationStatsView(APIView):
    """GET /api/monetization/stats/public/ — social proof checkout (sans auth)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        days = 7
        try:
            raw = request.query_params.get('days', '7')
            days = max(1, min(30, int(raw)))
        except (TypeError, ValueError):
            days = 7
        boosts = total_boosts_activated(days=days)
        return Response(
            {
                'boosts_activated_7d': boosts,
                'boosts_activated_period': boosts,
                'period_days': days,
            }
        )


class CheckoutPendingRecapView(APIView):
    """POST /api/monetization/checkout/pending-recap/ — email récap + lien retry 1-click."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        flow = str(request.data.get('flow') or 'premium').strip().lower()
        if flow not in ('premium', 'boost', 'campaign', 'tip'):
            flow = 'premium'
        transaction_id = str(request.data.get('transaction_id') or '').strip()
        platform = str(request.data.get('platform') or 'web').strip().lower()

        base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/') or 'http://localhost:5174'
        scheme = str(getattr(settings, 'MOBILE_APP_SCHEME', 'fotoce')).strip().rstrip(':') or 'fotoce'

        if platform in ('mobile', 'app', 'ios', 'android'):
            if transaction_id:
                retry_url = f'{scheme}://checkout/return?flow={flow}&transaction_id={transaction_id}'
            else:
                retry_url = f'{scheme}://checkout/return?flow={flow}'
        elif transaction_id:
            retry_url = f'{base}/checkout/return?flow={flow}&transaction_id={transaction_id}'
        elif flow == 'premium':
            retry_url = f'{base}/premium'
        elif flow == 'boost':
            retry_url = f'{base}/promote?tab=boost'
        elif flow == 'campaign':
            retry_url = f'{base}/promote?tab=stats'
        else:
            retry_url = base

        user = request.user
        email = (getattr(user, 'email', None) or '').strip()
        if not email:
            return Response({'detail': 'Email manquant.'}, status=status.HTTP_400_BAD_REQUEST)

        subject = 'Fotoce — finalisez votre paiement'
        body = (
            f'Bonjour,\n\n'
            f'Votre paiement Fotoce ({flow}) est en cours de validation.\n'
            f'Cliquez pour reprendre en un clic :\n{retry_url}\n\n'
            f'Si le paiement a déjà abouti, ignorez ce message.\n\n'
            f'— L’équipe Fotoce'
        )
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@fotoce.app'
        try:
            send_mail(subject, body, from_email, [email], fail_silently=False)
        except Exception:
            logger.exception('checkout pending recap email failed user_id=%s', user.id)
            return Response(
                {'detail': 'Envoi email impossible.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'ok': True, 'retry_url': retry_url})
