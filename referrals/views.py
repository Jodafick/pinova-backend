from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from pinova_backend.observability.analytics import capture_referral_link_opened

from .services import (
    build_public_resolve_payload,
    build_me_referral_payload,
    build_referral_leaderboard_http_payload,
    normalize_referral_code,
    record_referral_event,
    referral_signup_reward_bundle_total,
    store_referral_intent,
    _lookup_referrer_by_code,
)
from .models import ReferralAttribution, ReferralEvent


class ReferralIntentView(APIView):
    """Enregistre un code referral avant inscription (session web + device mobile)."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code') or request.data.get('ref') or ''
        device = (request.data.get('device_binding_id') or '').strip()[:128]
        session_key = ''
        if hasattr(request, 'session'):
            if not request.session.session_key:
                request.session.create()
            session_key = request.session.session_key or ''

        utm = request.data.get('utm')
        if utm is not None and not isinstance(utm, dict):
            utm = {}

        row = store_referral_intent(
            code_raw=str(code),
            session_key=session_key,
            device_binding_id=device,
            utm=utm if isinstance(utm, dict) else {},
        )
        if not row:
            return Response(
                {'detail': 'code et (session ou device_binding_id) requis'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ref_user = _lookup_referrer_by_code(row.code_normalized)
        from contests.services import get_active_contest_settings

        contest = get_active_contest_settings()
        if ref_user:
            record_referral_event(
                event_type=ReferralEvent.TYPE_LINK_OPENED,
                referee=None,
                referrer=ref_user,
                metadata={'intent_id': row.id},
                contest=contest,
            )
            distinct = device or session_key or f'intent-{row.id}'
            capture_referral_link_opened(
                distinct_id=distinct,
                ref_code=row.code_normalized,
                referrer_id=ref_user.id,
            )

        return Response(
            {
                'ok': True,
                'expires_at': row.expires_at.isoformat(),
                'code': row.code_normalized,
            },
            status=status.HTTP_201_CREATED,
        )


class ReferralResolveView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, code: str):
        payload = build_public_resolve_payload(code=code)
        if not payload:
            return Response({'valid': False}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)


class ReferralMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(build_me_referral_payload(request.user, request))


class ReferralMyRefereesView(APIView):
    """Filleuls attribués au parrain connecté (historique + statuts)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            ReferralAttribution.objects.filter(referrer=request.user)
            .select_related('referee')
            .order_by('-created_at')[:200]
        )
        bundle = referral_signup_reward_bundle_total()
        return Response(
            {
                'results': [
                    {
                        'id': a.id,
                        'referee_username': a.referee.username,
                        'status': a.status,
                        'source': a.source,
                        'created_at': a.created_at.isoformat() if a.created_at else None,
                        'activated_at': a.activated_at.isoformat() if a.activated_at else None,
                        'email_verified_at': a.email_verified_at.isoformat() if a.email_verified_at else None,
                        'rewards_granted_at': a.rewards_granted_at.isoformat() if a.rewards_granted_at else None,
                        'reward_points_credited': bundle if a.rewards_granted_at else 0.0,
                        'reward_points_pending': bundle
                        if (a.status == ReferralAttribution.STATUS_ACTIVE and not a.rewards_granted_at)
                        else 0.0,
                    }
                    for a in rows
                ],
            },
        )


class ReferralLeaderboardView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cid = request.query_params.get('contest_id')
        contest_id = int(cid) if cid and str(cid).isdigit() else None
        raw_limit = request.query_params.get('limit', '50')
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 50
        payload = build_referral_leaderboard_http_payload(request, contest_id=contest_id, limit=limit)
        return Response(payload)


class ReferralUniversalRedirectView(APIView):
    """Redirection HTTP vers l’inscription web avec ?ref= (Universal Link fallback)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, code: str):
        base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5174').rstrip('/')
        c = normalize_referral_code(code)
        target = f'{base}/register?ref={c}' if c else f'{base}/register'
        return HttpResponseRedirect(target)
