import logging
import os

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from fotos.models import Foto

from .fedapay_client import create_fedapay_checkout, fedapay_headers, payments_sandbox_allowed
from .models import BoostPackage, PartnerCampaign, FotoBoost, FotoPromoCampaign
from .serializers import (
    BoostPackageSerializer,
    PartnerCampaignSerializer,
    PartnerCampaignWriteSerializer,
    FotoBoostHistorySerializer,
    FotoPromoCampaignSerializer,
    FotoPromoCampaignWriteSerializer,
)
from .boost_catalog import PACKAGE_KIND_BOOST, PACKAGE_KIND_CAMPAIGN, active_packages_for_kind, package_allows_kind
from .boost_estimate import estimate_boost_reach
from .services import activate_foto_boost, activate_foto_promo_campaign, network_ad_config_payload, pick_contextual_ad
from .social_proof import enrich_boost_packages
from .targeting import targeting_options_payload

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
        kind = (request.query_params.get('kind') or request.query_params.get('package_kind') or '').strip()
        rows = list(active_packages_for_kind(kind or None))
        return Response({'results': enrich_boost_packages(rows, request.user)})


class BoostReachEstimateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, foto_slug: str):
        foto = get_object_or_404(Foto, slug=foto_slug)
        if foto.author_id != request.user.id:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        package_slug = (request.query_params.get('package') or request.query_params.get('package_slug') or '').strip()
        package = BoostPackage.objects.filter(slug=package_slug, is_active=True).first()
        duration_hours = package.duration_hours if package else 72
        if not package:
            try:
                duration_hours = max(1, int(request.query_params.get('duration_hours') or 72))
            except (TypeError, ValueError):
                duration_hours = 72
        payload = estimate_boost_reach(pin, duration_hours)
        if package:
            payload['package_slug'] = package.slug
        return Response(payload)


class FotoBoostCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, foto_slug: str):
        foto = get_object_or_404(Foto, slug=foto_slug)
        if foto.author_id != request.user.id:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        package_slug = (request.data.get('package') or request.data.get('package_slug') or '').strip()
        package = BoostPackage.objects.filter(slug=package_slug, is_active=True).first()
        if not package or not package_allows_kind(package, PACKAGE_KIND_BOOST):
            return Response({'error': 'Invalid package'}, status=status.HTTP_400_BAD_REQUEST)

        boost = FotoBoost.objects.create(
            foto=pin,
            owner=request.user,
            package=package,
            status=FotoBoost.STATUS_PENDING,
        )

        secret = fedapay_headers()
        if not secret:
            if payments_sandbox_allowed():
                activate_foto_boost(boost)
                return Response({
                    'status': 'active',
                    'boost_id': boost.id,
                    'ends_at': boost.ends_at.isoformat() if boost.ends_at else None,
                    'sandbox': True,
                })
            return Response({'error': 'Payments not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        from accounts.auth_tokens import checkout_return_url

        checkout = create_fedapay_checkout(
            request=request,
            description=f'Fotoce boost · {package.label} · Foto {boost.pin.slug}',
            amount=int(package.amount),
            currency_iso=package.currency_iso,
            callback_url=os.environ.get('FEDAPAY_BOOST_CALLBACK_URL') or checkout_return_url('boost', request=request),
        )
        if checkout.get('error'):
            boost.status = FotoBoost.STATUS_CANCELED
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


class MyFotoBoostsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            FotoBoost.objects.filter(owner=request.user)
            .select_related('pin', 'package')
            .order_by('-created_at')[:50]
        )
        ser = FotoBoostHistorySerializer(rows, many=True)
        return Response({'results': ser.data})


class ContextualAdView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        placement = (request.query_params.get('placement') or 'pin_detail').strip()
        topic = (request.query_params.get('topic') or '').strip()
        row = pick_contextual_ad(request, placement=placement, topic=topic)
        if not row:
            return Response({'ad': None})
        return Response({'ad': row})


class NetworkAdConfigView(APIView):
    """Config pubs réseau (AdSense / AdMob) — respecte plan et `ad_ads_enabled`."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(network_ad_config_payload(request))


class CampaignTargetingOptionsView(APIView):
    """Dimensions de ciblage disponibles pour les campagnes créateur."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from fotos.models import Topic

        topics = [
            {'slug': t.name.strip().lower(), 'name': t.name}
            for t in Topic.objects.order_by('name')[:80]
        ]
        return Response(targeting_options_payload(topics))


class FotoPromoCampaignListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            FotoPromoCampaign.objects.filter(owner=request.user)
            .select_related('pin', 'package')
            .order_by('-created_at')[:100]
        )
        ser = FotoPromoCampaignSerializer(rows, many=True, context={'request': request})
        return Response({'results': ser.data})

    def post(self, request):
        ser = FotoPromoCampaignWriteSerializer(data=request.data, context={'request': request})
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        campaign = ser.save()
        package = campaign.package
        secret = fedapay_headers()
        if not secret:
            if payments_sandbox_allowed():
                activate_foto_promo_campaign(campaign)
                out = FotoPromoCampaignSerializer(campaign, context={'request': request})
                return Response({**out.data, 'status': 'active', 'sandbox': True}, status=status.HTTP_201_CREATED)
            return Response({'error': 'Payments not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        promo_label = (campaign.headline or '').strip() or (
            f'pin {campaign.pin.slug}' if campaign.foto_id else 'campagne'
        )
        from accounts.auth_tokens import checkout_return_url

        checkout = create_fedapay_checkout(
            request=request,
            description=f'Fotoce promo · {package.label} · {promo_label}',
            amount=int(package.amount),
            currency_iso=package.currency_iso,
            callback_url=os.environ.get('FEDAPAY_PROMO_CALLBACK_URL') or checkout_return_url('campaign', request=request),
        )
        if checkout.get('error'):
            campaign.status = FotoPromoCampaign.STATUS_CANCELED
            campaign.save(update_fields=['status', 'updated_at'])
            return Response(checkout, status=status.HTTP_502_BAD_GATEWAY)
        campaign.fedapay_transaction_id = checkout['transaction_id']
        campaign.save(update_fields=['fedapay_transaction_id', 'updated_at'])
        out = FotoPromoCampaignSerializer(campaign, context={'request': request})
        return Response({
            **out.data,
            'status': 'pending',
            'checkout_url': checkout.get('checkout_url'),
            'transaction_id': checkout['transaction_id'],
        }, status=status.HTTP_201_CREATED)


class FotoPromoCampaignDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, campaign_id: int):
        campaign = get_object_or_404(FotoPromoCampaign, pk=campaign_id, owner=request.user)
        if 'status' in request.data:
            new_status = str(request.data.get('status') or '').strip()
            if new_status in (FotoPromoCampaign.STATUS_PAUSED, FotoPromoCampaign.STATUS_ACTIVE):
                campaign.status = new_status
                campaign.save(update_fields=['status', 'updated_at'])
        ser = FotoPromoCampaignSerializer(campaign, context={'request': request})
        return Response(ser.data)


class FotoPromoCampaignClickView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, campaign_id: int):
        from django.db.models import F

        campaign = FotoPromoCampaign.objects.select_related('pin').filter(
            pk=campaign_id,
            status=FotoPromoCampaign.STATUS_ACTIVE,
        ).first()
        if not campaign:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        updates = {'clicks': F('clicks') + 1}
        if campaign.foto_id:
            updates['pin_views'] = F('pin_views') + 1
        FotoPromoCampaign.objects.filter(pk=campaign_id).update(**updates)
        cta_url = (campaign.cta_url or '').strip()
        foto_slug = campaign.pin.slug if campaign.foto_id else ''
        return Response({'ok': True, 'foto_slug': foto_slug, 'cta_url': cta_url})


def approve_boost_payment(
    transaction_id: str,
    webhook_payload: dict,
    *,
    skip_amount_check: bool = False,
) -> str:
    """Appelé depuis le webhook FedaPay global."""
    from monetization.fedapay_webhook import amounts_match, webhook_amount

    promo = FotoPromoCampaign.objects.filter(fedapay_transaction_id=transaction_id).select_related('package').first()
    boost = FotoBoost.objects.filter(fedapay_transaction_id=transaction_id).select_related('package').first()
    target = promo or boost
    if not target:
        return 'ignored'
    wh_amount = webhook_amount(webhook_payload)
    if not skip_amount_check and not amounts_match(target.package.amount, wh_amount):
        return 'amount_mismatch'
    if promo:
        activate_foto_promo_campaign(promo)
        return 'approved'
    activate_foto_boost(boost)
    return 'approved'
