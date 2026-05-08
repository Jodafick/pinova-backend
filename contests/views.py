from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ContestResult, ContestSettings, CreatorContestScore, LeaderboardEvent, PinContestScore
from .services import get_active_contest_settings


class CurrentContestView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'detail': 'No active contest'}, status=404)
        return Response(
            {
                'contest_key': contest.contest_key,
                'start_at': contest.start_at,
                'end_at': contest.end_at,
                'timezone': contest.timezone,
                'max_winners': contest.max_winners,
                'refresh_interval': contest.leaderboard_refresh_interval,
                'now': timezone.now(),
            }
        )


class LeaderboardPinsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'results': []})
        limit = min(max(int(request.query_params.get('limit', 100) or 100), 1), 200)
        rows = (
            PinContestScore.objects.filter(contest=contest)
            .select_related('pin', 'creator')
            .order_by('rank', '-adjusted_score')[:limit]
        )
        results = [
            {
                'pin_id': row.pin_id,
                'pin_slug': row.pin.slug,
                'pin_title': row.pin.title,
                'creator_id': row.creator_id,
                'creator_username': row.creator.username,
                'rank': row.rank,
                'previous_rank': row.previous_rank,
                'score': row.adjusted_score,
            }
            for row in rows
        ]
        return Response({'contest_key': contest.contest_key, 'results': results})


class LeaderboardCreatorsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'results': []})
        limit = min(max(int(request.query_params.get('limit', 100) or 100), 1), 200)
        rows = (
            CreatorContestScore.objects.filter(contest=contest)
            .select_related('creator')
            .order_by('rank', '-adjusted_score')[:limit]
        )
        results = [
            {
                'creator_id': row.creator_id,
                'creator_username': row.creator.username,
                'rank': row.rank,
                'previous_rank': row.previous_rank,
                'score': row.adjusted_score,
            }
            for row in rows
        ]
        return Response({'contest_key': contest.contest_key, 'results': results})


class LeaderboardEventsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'results': []})
        since = int(request.query_params.get('since', 0) or 0)
        limit = min(max(int(request.query_params.get('limit', 200) or 200), 1), 500)
        qs = LeaderboardEvent.objects.filter(contest=contest)
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
                        'entity_type': row.entity_type,
                        'entity_id': row.entity_id,
                        'payload': row.payload,
                        'created_at': row.created_at,
                    }
                    for row in rows
                ],
            }
        )


class ContestHistoryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, contest_key: str):
        contest = ContestSettings.objects.filter(contest_key=contest_key).first()
        if not contest:
            return Response({'detail': 'Contest not found'}, status=404)
        result = ContestResult.objects.filter(contest=contest).first()
        return Response(
            {
                'contest_key': contest.contest_key,
                'start_at': contest.start_at,
                'end_at': contest.end_at,
                'result': {
                    'winners': (result.winners_json if result else []),
                    'payouts': (result.payout_json if result else []),
                    'finalized_at': (result.finalized_at if result else None),
                },
            }
        )
