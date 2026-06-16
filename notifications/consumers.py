import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken

from fotoce_backend.websocket.auth import extract_ws_bearer_token, pick_accepted_subprotocol
from fotoce_backend.websocket.heartbeat import HeartbeatMixin

from .realtime import notifications_group_name


class NotificationConsumer(HeartbeatMixin, AsyncWebsocketConsumer):
    async def connect(self):
        token, _source = extract_ws_bearer_token(self.scope)
        if not token:
            await self.close(code=4401)
            return
        user = await self._get_user_from_access_token(token)
        if not user:
            await self.close(code=4401)
            return
        self.user_id = int(user.id)
        self.group_name = notifications_group_name(self.user_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        subprotocol = pick_accepted_subprotocol(self.scope)
        await self.accept(subprotocol=subprotocol)
        await self.start_heartbeat()

    async def disconnect(self, close_code):
        await self.stop_heartbeat()
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if await self.handle_heartbeat_message(text_data):
            return

    async def notification_event(self, event):
        payload = event.get('payload') or {}
        await self.send(text_data=json.dumps({'event': payload}))

    @database_sync_to_async
    def _get_user_from_access_token(self, token: str):
        try:
            access = AccessToken(token)
            user_id = int(access.get('user_id'))
        except Exception:
            return None
        return User.objects.filter(id=user_id, is_active=True).only('id').first()
