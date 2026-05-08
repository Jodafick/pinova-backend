from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from pinova_backend.media_cache import build_versioned_media_url
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
                'refresh_interval': max(1, min(300, int(contest.leaderboard_refresh_interval or 3))),
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
        ordered = list(
            PinContestScore.objects.filter(contest=contest, pin__is_story=False)
            .select_related('pin', 'creator')
            .order_by('-adjusted_score', 'rank', 'pin_id')
        )
        best_by_creator = {}
        for row in ordered:
            if row.creator_id in best_by_creator:
                continue
            best_by_creator[row.creator_id] = row
            if len(best_by_creator) >= limit:
                break
        selected_rows = sorted(
            best_by_creator.values(),
            key=lambda r: (-float(r.adjusted_score), r.rank or 999_999, r.pin_id),
        )

        results = []
        for idx, row in enumerate(selected_rows):
            likes = int(row.total_likes or 0)
            views = int(row.total_views or 0)
            shares = int(row.total_shares or 0)
            saves = int(row.total_saves or 0)
            comments = int(row.total_comments or 0)
            results.append(
                {
                    'pin_id': row.pin_id,
                    'pin_slug': row.pin.slug,
                    'pin_title': row.pin.title,
                    'pin_image_url': build_versioned_media_url(request, row.pin.image),
                    'creator_id': row.creator_id,
                    'creator_username': row.creator.username,
                    'rank': idx + 1,
                    'previous_rank': row.previous_rank,
                    'score': row.adjusted_score,
                    'likes': likes,
                    'views': views,
                    'shares': shares,
                    'saves': saves,
                    'comments': comments,
                    'engagement_total': likes + views + shares + saves + comments,
                }
            )
        return Response({'contest_key': contest.contest_key, 'results': results})


class ContestArchiveIndexView(APIView):
    """Mois passés ayant un résultat finalisé (`ContestResult`)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rows = ContestResult.objects.select_related('contest').order_by('-contest__start_at')[:72]
        return Response(
            {
                'results': [
                    {
                        'contest_key': r.contest.contest_key,
                        'start_at': r.contest.start_at,
                        'end_at': r.contest.end_at,
                        'finalized_at': r.finalized_at,
                    }
                    for r in rows
                ]
            }
        )


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
