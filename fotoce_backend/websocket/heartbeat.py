"""Mixin heartbeat WebSocket — ping serveur 30s, déconnexion stale 90s."""

from __future__ import annotations

import asyncio
import time

from django.conf import settings


def _heartbeat_interval() -> float:
    return float(getattr(settings, 'WS_HEARTBEAT_INTERVAL', 30))


def _stale_timeout() -> float:
    return float(getattr(settings, 'WS_STALE_TIMEOUT', 90))


class HeartbeatMixin:
    """À mélanger avec AsyncWebsocketConsumer — appeler start/stop depuis connect/disconnect."""

    _heartbeat_task: asyncio.Task | None = None
    _last_seen: float = 0.0

    async def start_heartbeat(self) -> None:
        self._last_seen = time.monotonic()
        await self.stop_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        task = getattr(self, '_heartbeat_task', None)
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._heartbeat_task = None

    def touch_heartbeat(self) -> None:
        self._last_seen = time.monotonic()

    async def handle_heartbeat_message(self, text_data: str | None) -> bool:
        """Traite ping/pong ; retourne True si le message était un heartbeat."""
        if text_data == 'ping':
            self.touch_heartbeat()
            await self.send(text_data='pong')
            return True
        if text_data == 'pong':
            self.touch_heartbeat()
            return True
        if text_data is not None:
            self.touch_heartbeat()
        return False

    async def _heartbeat_loop(self) -> None:
        interval = _heartbeat_interval()
        stale = _stale_timeout()
        try:
            while True:
                await asyncio.sleep(interval)
                if time.monotonic() - self._last_seen > stale:
                    await self.close(code=4000)
                    break
                await self.send(text_data='ping')
        except asyncio.CancelledError:
            pass
