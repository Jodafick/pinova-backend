"""Endpoints authentifiés pour l’assistant Ads Manager (campagnes, créatifs, annonces)."""

from django.db import transaction
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ads import constants as ac
from ads.manager_serializers import (
    ManagerAdWriteSerializer,
    ManagerCampaignWriteSerializer,
    ManagerCreativeWriteSerializer,
)
from ads.models import Advertiser, BusinessAccount
from ads.serializers import NativeAdSerializer


class ManagerBootstrapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        with transaction.atomic():
            ba = (
                BusinessAccount.objects.select_for_update()
                .filter(owner=user)
                .select_related('advertiser')
                .first()
            )
            if not ba:
                adv = Advertiser.objects.create(
                    name=(user.get_full_name() or user.username or 'Annonceur')[:255],
                    contact_email=(user.email or 'noreply@pinova.local')[:254],
                    status=ac.ADVERTISER_STATUS_ACTIVE,
                )
                ba = BusinessAccount.objects.create(
                    owner=user,
                    advertiser=adv,
                    display_name=(user.get_full_name() or user.username or 'Mon compte pub')[:255],
                )
        return Response(
            {
                'business_account': {
                    'id': str(ba.pk),
                    'display_name': ba.display_name,
                    'advertiser_id': str(ba.advertiser_id),
                }
            }
        )


class ManagerCampaignCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        ser = ManagerCampaignWriteSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            campaign = ser.save()
        return Response(
            {
                'id': str(campaign.pk),
                'name': campaign.name,
                'status': campaign.status,
                'objective': campaign.objective,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagerCreativeCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        ser = ManagerCreativeWriteSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        creative = ser.save()
        return Response(
            {
                'id': str(creative.pk),
                'headline': creative.headline,
                'media_image': request.build_absolute_uri(creative.media_image.url)
                if creative.media_image
                else None,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagerAdCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        ser = ManagerAdWriteSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            ad = ser.save()
        return Response(NativeAdSerializer(ad, context={'request': request}).data, status=status.HTTP_201_CREATED)
