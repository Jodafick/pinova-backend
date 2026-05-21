from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .reference_data import interest_catalog_for_lang


class ReferenceInterestsView(APIView):
    """GET /api/reference/interests/?lang=fr — catalogue onboarding (source unique)."""

    permission_classes = [AllowAny]

    def get(self, request):
        lang = (request.query_params.get('lang') or request.headers.get('X-Pinova-Lang') or 'fr').strip()
        return Response({'results': interest_catalog_for_lang(lang)})
