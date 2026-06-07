import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from contests.services import get_active_contest_settings
from pinova_backend.websocket.heartbeat import HeartbeatMixin
from pinova_backend.websocket.ratelimit import allow_ws_connection

from .models import ReferralLeaderboardEvent


class ReferralLeaderboardConsumer(HeartbeatMixin, AsyncWebsocketConsumer):
    async def connect(self):
        if not allow_ws_connection(self.scope, namespace='referral_leaderboard'):
            await self.close(code=4429)
            return
        self.contest = await self._get_active_contest()
        if not self.contest:
            await self.close(code=4404)
            return
        self.group_name = f'referral_{self.contest.contest_key.replace("-", "_")}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.start_heartbeat()

        query = parse_qs((self.scope.get('query_string') or b'').decode('utf-8'))
        try:
            since = int((query.get('since') or ['0'])[0] or 0)
        except (TypeError, ValueError):
            since = 0
        backlog = await self._get_backlog(since=since, contest_id=self.contest.id)
        if backlog:
            await self.send(text_data=json.dumps({'events': backlog}))

    async def disconnect(self, close_code):
        await self.stop_heartbeat()
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        await self.handle_heartbeat_message(text_data)

    async def referral_event(self, event):
        payload = event.get('payload') or {}
        await self.send(text_data=json.dumps({'event': payload}))

    @database_sync_to_async
    def _get_active_contest(self):
        return get_active_contest_settings()

    @database_sync_to_async
    def _get_backlog(self, *, since: int, contest_id: int):
        rows = (
            ReferralLeaderboardEvent.objects.filter(contest_id=contest_id, sequence__gt=since)
            .order_by('sequence')[:300]
        )
        return [
            {
                'sequence': row.sequence,
                'event_type': row.event_type,
                'entity_id': row.entity_id,
                'payload': row.payload,
                'created_at': row.created_at.isoformat(),
            }
            for row in rows
        ]
