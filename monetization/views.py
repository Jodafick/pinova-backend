import logging
import os

import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from pins.models import Pin

from .models import BoostPackage, PartnerCampaign, PinBoost
from .serializers import (
    BoostPackageSerializer,
    PartnerCampaignSerializer,
    PartnerCampaignWriteSerializer,
)
from .services import activate_pin_boost

logger = logging.getLogger(__name__)


class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class PartnerCampaignListCreateView(APIView):
    """Liste publique (staff) + création simple réservée au staff."""

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsStaffUser()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        rows = PartnerCampaign.objects.all()[:100]
        ser = PartnerCampaignSerializer(rows, many=True, context={'request': request})
        return Response({'results': ser.data})

    def post(self, request):
        ser = PartnerCampaignWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        campaign = ser.save(created_by=request.user)
        out = PartnerCampaignSerializer(campaign, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class PartnerCampaignDetailView(APIView):
    permission_classes = [IsStaffUser]

    def patch(self, request, campaign_id: int):
        campaign = get_object_or_404(PartnerCampaign, pk=campaign_id)
        ser = PartnerCampaignWriteSerializer(campaign, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        return Response(PartnerCampaignSerializer(campaign, context={'request': request}).data)

    def delete(self, request, campaign_id: int):
        campaign = get_object_or_404(PartnerCampaign, pk=campaign_id)
        campaign.is_active = False
        campaign.save(update_fields=['is_active', 'updated_at'])
        return Response({'ok': True})


class PartnerCampaignClickView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, campaign_id: int):
        from django.db.models import F

        updated = PartnerCampaign.objects.filter(pk=campaign_id, is_active=True).update(
            clicks=F('clicks') + 1,
        )
        if not updated:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'ok': True})


class BoostPackageListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rows = BoostPackage.objects.filter(is_active=True)
        return Response({'results': BoostPackageSerializer(rows, many=True).data})


class PinBoostCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pin_slug: str):
        pin = get_object_or_404(Pin, slug=pin_slug)
        if pin.author_id != request.user.id:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        package_slug = (request.data.get('package') or request.data.get('package_slug') or '').strip()
        package = BoostPackage.objects.filter(slug=package_slug, is_active=True).first()
        if not package:
            return Response({'error': 'Invalid package'}, status=status.HTTP_400_BAD_REQUEST)

        boost = PinBoost.objects.create(
            pin=pin,
            owner=request.user,
            package=package,
            status=PinBoost.STATUS_PENDING,
        )

        secret = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
        if not secret:
            if settings.DEBUG or os.environ.get('BOOST_SANDBOX_ACTIVATE', '').lower() == 'true':
                activate_pin_boost(boost)
                return Response({
                    'status': 'active',
                    'boost_id': boost.id,
                    'ends_at': boost.ends_at.isoformat() if boost.ends_at else None,
                    'sandbox': True,
                })
            return Response({'error': 'Payments not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        checkout = _create_fedapay_boost_checkout(request, boost, package)
        if checkout.get('error'):
            boost.status = PinBoost.STATUS_CANCELED
            boost.save(update_fields=['status', 'updated_at'])
            return Response(checkout, status=status.HTTP_502_BAD_GATEWAY)
        boost.fedapay_transaction_id = checkout['transaction_id']
        boost.save(update_fields=['fedapay_transaction_id', 'updated_at'])
        return Response({
            'status': 'pending',
            'boost_id': boost.id,
            'checkout_url': checkout.get('checkout_url'),
            'transaction_id': checkout['transaction_id'],
        })


def _fedapay_base_url():
    env = os.environ.get('FEDAPAY_ENV', 'sandbox').strip().lower()
    if env == 'live':
        return 'https://api.fedapay.com/v1'
    return 'https://sandbox-api.fedapay.com/v1'


def _create_fedapay_boost_checkout(request, boost: PinBoost, package: BoostPackage) -> dict:
    secret = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
    headers = {
        'Authorization': f'Bearer {secret}',
        'Content-Type': 'application/json',
    }
    default_callback = f"{str(settings.FRONTEND_URL).rstrip('/')}/profile/{request.user.username}"
    callback_url = os.environ.get('FEDAPAY_BOOST_CALLBACK_URL') or default_callback
    payload = {
        'description': f'Pinova boost · {package.label} · pin {boost.pin.slug}',
        'amount': int(package.amount),
        'currency': {'iso': package.currency_iso},
        'callback_url': callback_url,
        'customer': {
            'email': request.user.email or f'{request.user.username}@pinova.local',
            'firstname': request.user.username[:50],
            'lastname': 'Pinova',
        },
    }
    try:
        create_resp = requests.post(
            f'{_fedapay_base_url()}/transactions',
            json=payload,
            headers=headers,
            timeout=30,
        )
        if create_resp.status_code >= 400:
            logger.error('FedaPay boost create failed: %s', create_resp.text)
            return {'error': 'FedaPay transaction create failed'}
        body = create_resp.json()
        tx_id = _extract_tx_id(body)
        if not tx_id:
            return {'error': 'Invalid FedaPay response'}
        token_resp = requests.post(
            f'{_fedapay_base_url()}/transactions/{tx_id}/token',
            headers=headers,
            timeout=30,
        )
        checkout_url = None
        if token_resp.status_code < 400:
            token_body = token_resp.json()
            checkout_url = _extract_checkout_url(token_body)
        return {'transaction_id': str(tx_id), 'checkout_url': checkout_url}
    except requests.RequestException as exc:
        logger.exception('FedaPay boost request failed: %s', exc)
        return {'error': 'FedaPay unavailable'}


def _extract_tx_id(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get('id'):
        return payload.get('id')
    for key in ('transaction', 'data', 'v1/transaction'):
        nested = payload.get(key)
        if isinstance(nested, dict) and nested.get('id'):
            return nested.get('id')
    return None


def _extract_checkout_url(payload):
    if not isinstance(payload, dict):
        return None
    for key in ('url', 'payment_url', 'redirect_url'):
        if payload.get(key):
            return payload.get(key)
    for key in ('token', 'data'):
        nested = payload.get(key)
        if isinstance(nested, dict):
            for nk in ('url', 'payment_url', 'redirect_url'):
                if nested.get(nk):
                    return nested.get(nk)
    return None


def approve_boost_payment(transaction_id: str, webhook_payload: dict) -> str:
    """Appelé depuis le webhook FedaPay global."""
    boost = PinBoost.objects.filter(fedapay_transaction_id=transaction_id).first()
    if not boost:
        return 'ignored'
    activate_pin_boost(boost)
    return 'approved'
