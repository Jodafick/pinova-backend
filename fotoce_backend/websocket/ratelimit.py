"""Rate limit connexions WebSocket publiques (leaderboards)."""

from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache

from fotoce_backend.websocket.auth import _client_ip


def _limit() -> int:
    return int(getattr(settings, 'WS_LEADERBOARD_CONN_LIMIT', 10))


def _window() -> int:
    return int(getattr(settings, 'WS_LEADERBOARD_CONN_WINDOW', 60))


def allow_ws_connection(scope, *, namespace: str) -> bool:
    """
    Limite les nouvelles connexions WS par IP (fenêtre glissante par minute).
    Retourne False si la limite est atteinte.
    """
    ip = _client_ip(scope)
    window = _window()
    bucket = int(time.time()) // window
    key = f'ws_conn_rl:{namespace}:{ip}:{bucket}'
    try:
        count = cache.get(key, 0)
        if count >= _limit():
            return False
        cache.set(key, count + 1, timeout=window + 5)
        return True
    except Exception:
        # Ne pas bloquer si le cache est indisponible.
        return True
