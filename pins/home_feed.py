"""Pagination DB-native pour home_feed (mélange following / discover 50/50)."""

from __future__ import annotations

from typing import Literal

SourceSlot = tuple[Literal['following', 'discover'], int]


def home_feed_total_count(following_count: int, discover_count: int) -> int:
    if following_count <= 0:
        return discover_count
    return following_count + discover_count


def compute_interleave_slots(
    following_count: int,
    discover_count: int,
    global_start: int,
    limit: int,
) -> list[SourceSlot]:
    """
    Reproduit l'entrelacement historique (following puis discover par tour de boucle).
    Retourne les indices source pour la fenêtre [global_start, global_start + limit).
    """
    if limit <= 0 or global_start < 0:
        return []
    if following_count <= 0:
        start = min(global_start, discover_count)
        end = min(global_start + limit, discover_count)
        return [('discover', i) for i in range(start, end)]

    fi, di, pos = 0, 0, 0
    slots: list[SourceSlot] = []
    while len(slots) < limit and (fi < following_count or di < discover_count):
        if fi < following_count:
            if pos >= global_start:
                slots.append(('following', fi))
            fi += 1
            pos += 1
            if len(slots) >= limit:
                break
        if di < discover_count:
            if pos >= global_start:
                slots.append(('discover', di))
            di += 1
            pos += 1
            if len(slots) >= limit:
                break
    return slots


def fetch_pins_for_slots(following_qs, discover_qs, slots: list[SourceSlot]):
    """Charge les pins pour une page via au plus deux requêtes DB (tranches contiguës)."""
    if not slots:
        return []

    following_indices = [idx for src, idx in slots if src == 'following']
    discover_indices = [idx for src, idx in slots if src == 'discover']

    following_map: dict[int, object] = {}
    if following_indices:
        lo, hi = min(following_indices), max(following_indices)
        for offset, pin in enumerate(following_qs[lo : hi + 1], start=lo):
            following_map[offset] = pin

    discover_map: dict[int, object] = {}
    if discover_indices:
        lo, hi = min(discover_indices), max(discover_indices)
        for offset, pin in enumerate(discover_qs[lo : hi + 1], start=lo):
            discover_map[offset] = pin

    page_pins = []
    for src, idx in slots:
        pin = following_map.get(idx) if src == 'following' else discover_map.get(idx)
        if pin is not None:
            page_pins.append(pin)
    return page_pins


def interleave_pin_lists(following_items, discover_items):
    """Référence Python pour tests — même algorithme que l'ancien home_feed."""
    if not following_items:
        return list(discover_items)
    mixed = []
    follow_idx = 0
    discover_idx = 0
    while follow_idx < len(following_items) or discover_idx < len(discover_items):
        if follow_idx < len(following_items):
            mixed.append(following_items[follow_idx])
            follow_idx += 1
        if discover_idx < len(discover_items):
            mixed.append(discover_items[discover_idx])
            discover_idx += 1
    return mixed
