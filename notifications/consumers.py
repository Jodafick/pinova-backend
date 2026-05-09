import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken

from .realtime import notifications_group_name


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = await self._resolve_user_from_scope()
        if not user:
            await self.close(code=4401)
            return
        self.user_id = int(user.id)
        self.group_name = notifications_group_name(self.user_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == 'ping':
            await self.send(text_data='pong')

    async def notification_event(self, event):
        payload = event.get('payload') or {}
        await self.send(text_data=json.dumps({'event': payload}))

    async def _resolve_user_from_scope(self):
        token = self._extract_bearer_token()
        if not token:
            return None
        return await self._get_user_from_access_token(token)

    def _extract_bearer_token(self) -> str:
        query = parse_qs((self.scope.get('query_string') or b'').decode('utf-8'))
        token_qs = str((query.get('token') or [''])[0] or '').strip()
        if token_qs:
            return token_qs

        headers = self.scope.get('headers') or []
        for key, val in headers:
            if key.lower() != b'authorization':
                continue
            raw = val.decode('utf-8', errors='ignore').strip()
            if raw.lower().startswith('bearer '):
                return raw[7:].strip()
        return ''

    @database_sync_to_async
    def _get_user_from_access_token(self, token: str):
        try:
            access = AccessToken(token)
            user_id = int(access.get('user_id'))
        except Exception:
            return None
        return User.objects.filter(id=user_id, is_active=True).only('id').first()
