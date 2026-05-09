import uuid

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ads import constants as ac
from ads.models import Ad, AdHide, AdPendingEvent, AdReport
from ads.serializers import (
    DeliveryRequestSerializer,
    HideSerializer,
    NativeAdSerializer,
    PendingEventInSerializer,
    ReportSerializer,
)
from ads.services.delivery import select_native_ads
from ads.services.geo import mapbox_geocode_forward, mapbox_reverse_geocode


class NativeCandidatesView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        ser = DeliveryRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        ads, meta = select_native_ads(
            placement=data['placement'],
            user=request.user if request.user.is_authenticated else None,
            client=data.get('client') or {},
            limit=data.get('limit') or 2,
            session_depth=data.get('session_depth') or 0,
            request_id=uuid.uuid4(),
        )
        return Response({'ads': NativeAdSerializer(ads, many=True, context={'request': request}).data, 'meta': meta})


class PendingEventsBatchView(APIView):
    """Ingestion batch async (impressions, vues, watch) — préférer cette route sous charge."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        events = request.data.get('events') if isinstance(request.data, dict) else None
        if not isinstance(events, list):
            return Response({'detail': 'events must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        created = 0
        for item in events[:200]:
            evs = PendingEventInSerializer(data=item)
            if not evs.is_valid():
                continue
            v = evs.validated_data
            AdPendingEvent.objects.create(
                event_type=v['event_type'],
                payload=v['payload'],
                dedupe_key=v.get('dedupe_key') or '',
            )
            created += 1
        return Response({'queued': created}, status=status.HTTP_201_CREATED)


class GeoAutocompleteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        q = (request.query_params.get('q') or '').strip()
        country = (request.query_params.get('country') or '').strip() or None
        if len(q) < 2:
            return Response({'results': []})
        try:
            results = mapbox_geocode_forward(q, limit=8, country=country)
        except Exception as exc:
            return Response({'detail': str(exc), 'results': []}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({'results': results})


class GeoReverseView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            lng = float(request.query_params.get('lng'))
            lat = float(request.query_params.get('lat'))
        except (TypeError, ValueError):
            return Response({'detail': 'lng and lat required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = mapbox_reverse_geocode(lng, lat)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({'result': res})


class AdHideView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        ser = HideSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ad = ser.validated_data['ad']
        AdHide.objects.get_or_create(
            user=request.user,
            ad=ad,
            defaults={'reason': ser.validated_data.get('reason') or ''},
        )
        return Response({'ok': True}, status=status.HTTP_201_CREATED)


class AdReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        ser = ReportSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        AdReport.objects.create(
            user=request.user,
            ad=ser.validated_data['ad'],
            reason=ser.validated_data['reason'],
            details=ser.validated_data.get('details') or '',
        )
        return Response({'ok': True}, status=status.HTTP_201_CREATED)


class AdDetailPublicView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, ad_id, *args, **kwargs):
        ad = get_object_or_404(Ad.objects.select_related('creative'), pk=ad_id, status=ac.AD_STATUS_ACTIVE)
        return Response(NativeAdSerializer(ad, context={'request': request}).data)
