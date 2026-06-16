from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from fotoce_backend.media_serving.cache import build_versioned_media_url
from .models import ContestResult, ContestSettings, CreatorContestScore, LeaderboardEvent, FotoContestScore
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
                'leaderboard_display_pins': max(1, min(int(contest.leaderboard_display_pins or 10), 500)),
                'refresh_interval': max(1, min(300, int(contest.leaderboard_refresh_interval or 3))),
                'now': timezone.now(),
            }
        )


def _serialize_foto_contest_row(request, row, rank_one_based):
    likes = int(row.total_likes or 0)
    views = int(row.total_views or 0)
    shares = int(row.total_shares or 0)
    saves = int(row.total_saves or 0)
    comments = int(row.total_comments or 0)
    return {
        'foto_id': row.foto_id,
        'foto_slug': row.pin.slug,
        'pin_title': row.pin.title,
        'pin_image_url': build_versioned_media_url(request, row.pin.image),
        'creator_id': row.creator_id,
        'creator_username': row.creator.username,
        'rank': rank_one_based,
        'previous_rank': row.previous_rank,
        'score': row.adjusted_score,
        'likes': likes,
        'views': views,
        'shares': shares,
        'saves': saves,
        'comments': comments,
        'engagement_total': likes + views + shares + saves + comments,
    }


class LeaderboardFotosView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        contest = get_active_contest_settings()
        if not contest:
            return Response({'contest_key': None, 'results': [], 'viewer': None})
        contest_cap = max(1, min(int(contest.leaderboard_display_pins or 10), 500))
        raw_limit = request.query_params.get('limit')
        if raw_limit is None or str(raw_limit).strip() == '':
            limit = contest_cap
        else:
            try:
                requested = int(raw_limit)
            except (TypeError, ValueError):
                requested = contest_cap
            limit = min(max(requested, 1), contest_cap)
        ordered = list(
            FotoContestScore.objects.filter(contest=contest, pin__is_story=False)
            .select_related('pin', 'creator')
            .order_by('-adjusted_score', 'rank', 'foto_id')
        )
        best_by_creator = {}
        for row in ordered:
            if row.creator_id in best_by_creator:
                continue
            best_by_creator[row.creator_id] = row

        selected_full = sorted(
            best_by_creator.values(),
            key=lambda r: (-float(r.adjusted_score), r.rank or 999_999, r.foto_id),
        )

        results = [
            _serialize_foto_contest_row(request, row, idx + 1) for idx, row in enumerate(selected_full[:limit])
        ]

        viewer_payload = None
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            uid = user.pk
            viewer_rank = None
            viewer_row = None
            for idx, row in enumerate(selected_full):
                if row.creator_id == uid:
                    viewer_row = row
                    viewer_rank = idx + 1
                    break
            if viewer_row is not None and viewer_rank is not None:
                viewer_payload = {
                    'ranked': True,
                    'rank': viewer_rank,
                    'in_displayed_top': viewer_rank <= limit,
                    'pin': _serialize_foto_contest_row(request, viewer_row, viewer_rank),
                }
            else:
                viewer_payload = {'ranked': False, 'rank': None, 'in_displayed_top': False, 'pin': None}

        return Response({'contest_key': contest.contest_key, 'results': results, 'viewer': viewer_payload})


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
