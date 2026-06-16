"""
Rang « affiché » du concours : un foto par créateur (meilleur score), comme le live LeaderboardFotos.
"""

from __future__ import annotations

from .models import ContestSettings, FotoContestScore


def dedup_best_foto_rows_for_contest(contest: ContestSettings) -> list[FotoContestScore]:
    ordered = list(
        FotoContestScore.objects.filter(contest=contest, pin__is_story=False)
        .select_related('foto', 'creator')
        .order_by('-adjusted_score', 'rank', 'foto_id')
    )
    best_by_creator: dict[int, FotoContestScore] = {}
    for row in ordered:
        if row.creator_id in best_by_creator:
            continue
        best_by_creator[row.creator_id] = row
    return sorted(
        best_by_creator.values(),
        key=lambda r: (-float(r.adjusted_score), r.rank or 999_999, r.foto_id),
    )


def display_rank_and_row_for_creator(contest: ContestSettings, creator_id: int) -> tuple[int | None, FotoContestScore | None]:
    rows = dedup_best_foto_rows_for_contest(contest)
    for idx, row in enumerate(rows):
        if row.creator_id == creator_id:
            return idx + 1, row
    return None, None


def display_rank_maps(contest: ContestSettings) -> tuple[dict[int, int], dict[int, FotoContestScore]]:
    rows = dedup_best_foto_rows_for_contest(contest)
    rank_by_creator: dict[int, int] = {}
    row_by_creator: dict[int, FotoContestScore] = {}
    for idx, row in enumerate(rows):
        rank_by_creator[row.creator_id] = idx + 1
        row_by_creator[row.creator_id] = row
    return rank_by_creator, row_by_creator
