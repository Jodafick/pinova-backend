"""
Rang « affiché » du concours : un pin par créateur (meilleur score), comme le live LeaderboardPins.
"""

from __future__ import annotations

from .models import ContestSettings, PinContestScore


def dedup_best_pin_rows_for_contest(contest: ContestSettings) -> list[PinContestScore]:
    ordered = list(
        PinContestScore.objects.filter(contest=contest, pin__is_story=False)
        .select_related('pin', 'creator')
        .order_by('-adjusted_score', 'rank', 'pin_id')
    )
    best_by_creator: dict[int, PinContestScore] = {}
    for row in ordered:
        if row.creator_id in best_by_creator:
            continue
        best_by_creator[row.creator_id] = row
    return sorted(
        best_by_creator.values(),
        key=lambda r: (-float(r.adjusted_score), r.rank or 999_999, r.pin_id),
    )


def display_rank_and_row_for_creator(contest: ContestSettings, creator_id: int) -> tuple[int | None, PinContestScore | None]:
    rows = dedup_best_pin_rows_for_contest(contest)
    for idx, row in enumerate(rows):
        if row.creator_id == creator_id:
            return idx + 1, row
    return None, None


def display_rank_maps(contest: ContestSettings) -> tuple[dict[int, int], dict[int, PinContestScore]]:
    rows = dedup_best_pin_rows_for_contest(contest)
    rank_by_creator: dict[int, int] = {}
    row_by_creator: dict[int, PinContestScore] = {}
    for idx, row in enumerate(rows):
        rank_by_creator[row.creator_id] = idx + 1
        row_by_creator[row.creator_id] = row
    return rank_by_creator, row_by_creator
