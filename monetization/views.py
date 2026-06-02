import logging
import os

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from pins.models import Pin

from .fedapay_client import create_fedapay_checkout, fedapay_headers, payments_sandbox_allowed
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

        secret = fedapay_headers()
        if not secret:
            if payments_sandbox_allowed():
                activate_pin_boost(boost)
                return Response({
                    'status': 'active',
                    'boost_id': boost.id,
                    'ends_at': boost.ends_at.isoformat() if boost.ends_at else None,
                    'sandbox': True,
                })
            return Response({'error': 'Payments not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        checkout = create_fedapay_checkout(
            request=request,
            description=f'Pinova boost · {package.label} · pin {boost.pin.slug}',
            amount=int(package.amount),
            currency_iso=package.currency_iso,
            callback_url=os.environ.get('FEDAPAY_BOOST_CALLBACK_URL')
            or f"{str(settings.FRONTEND_URL).rstrip('/')}/profile/{request.user.username}",
        )
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


def approve_boost_payment(transaction_id: str, webhook_payload: dict) -> str:
    """Appelé depuis le webhook FedaPay global."""
    boost = PinBoost.objects.filter(fedapay_transaction_id=transaction_id).first()
    if not boost:
        return 'ignored'
    activate_pin_boost(boost)
    return 'approved'
