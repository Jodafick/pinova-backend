from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from contests.models import ContestSettings
from contests.services import get_active_contest_settings

from .models import ReferralContestResult, ReferralLeaderboardEvent
from .services import build_referral_leaderboard_http_payload


class ReferralContestCurrentView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'detail': 'No active contest'}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                'contest_key': contest.contest_key,
                'contest_id': contest.id,
                'start_at': contest.start_at,
                'end_at': contest.end_at,
                'timezone': contest.timezone,
                'now': timezone.now(),
                'refresh_interval': max(1, min(300, int(contest.leaderboard_refresh_interval or 3))),
            },
        )


class ReferralContestArchivesView(APIView):
    """Mois passés avec résultat referral finalisé."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rows = ReferralContestResult.objects.select_related('contest').order_by('-contest__start_at')[:72]
        return Response(
            {
                'results': [
                    {
                        'contest_key': r.contest.contest_key,
                        'contest_id': r.contest_id,
                        'start_at': r.contest.start_at,
                        'end_at': r.contest.end_at,
                        'finalized_at': r.finalized_at,
                    }
                    for r in rows
                ],
            },
        )


class ReferralContestHistoryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, contest_key: str):
        contest = ContestSettings.objects.filter(contest_key=contest_key).first()
        if not contest:
            return Response({'detail': 'Contest not found'}, status=status.HTTP_404_NOT_FOUND)
        result = ReferralContestResult.objects.filter(contest=contest).first()
        return Response(
            {
                'contest_key': contest.contest_key,
                'start_at': contest.start_at,
                'end_at': contest.end_at,
                'result': {
                    'winners': (result.winners_json if result else []),
                    'leaderboard_snapshot': (result.leaderboard_snapshot_json if result else []),
                    'stats': (result.stats_json if result else {}),
                    'payouts': (result.payout_json if result else []),
                    'finalized_at': (result.finalized_at if result else None),
                },
            },
        )


class ReferralLeaderboardEventsPollView(APIView):
    """Polling HTTP aligné sur /api/contest/leaderboard/events (complément au WebSocket)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'contest_key': None, 'results': []})
        since = int(request.query_params.get('since', 0) or 0)
        limit = min(max(int(request.query_params.get('limit', 200) or 200), 1), 500)
        qs = ReferralLeaderboardEvent.objects.filter(contest=contest)
        if since > 0:
            qs = qs.filter(sequence__gt=since)
        rows = list(qs.order_by('sequence')[:limit])
        return Response(
            {
                'contest_key': contest.contest_key,
                'results': [
                    {
                        'sequence': row.sequence,
                        'event_type': row.event_type,
                        'entity_id': row.entity_id,
                        'payload': row.payload,
                        'created_at': row.created_at,
                    }
                    for row in rows
                ],
            },
        )
