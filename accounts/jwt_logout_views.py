"""Vues JWT Pinova — refresh et révocation globale."""

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


class LogoutAllView(APIView):
    """Invalide tous les refresh tokens émis pour l'utilisateur connecté."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        outstanding = OutstandingToken.objects.filter(user=request.user)
        revoked = 0
        for token in outstanding:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            if created:
                revoked += 1
        return Response({'ok': True, 'revoked': revoked}, status=status.HTTP_200_OK)
