"""Couche Redis Channels résiliente — retry après timeout connexion idle."""

from __future__ import annotations

import asyncio
import logging

from channels_redis.core import RedisChannelLayer
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeoutError

logger = logging.getLogger('fotoce.channel_layer')


class ResilientRedisChannelLayer(RedisChannelLayer):
    """Relance receive après timeout Redis (connexion idle Render / Elasticache)."""

    async def receive(self, channel):
        while True:
            try:
                return await super().receive(channel)
            except RedisTimeoutError:
                logger.warning('Redis channel receive timeout — retry channel=%s', channel)
                await asyncio.sleep(0.05)
            except ConnectionError as exc:
                logger.warning('Redis channel receive connection error — retry: %s', exc)
                await asyncio.sleep(0.25)
