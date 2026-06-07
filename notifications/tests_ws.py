"""Tests WebSocket Channels — auth, rate limit, broadcast multi-worker simulé."""
from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from notifications.realtime import notifications_group_name
from pinova_backend.websocket.auth import BEARER_SUBPROTOCOL_PREFIX, extract_ws_bearer_token
from pinova_backend.websocket.ratelimit import allow_ws_connection


def _jwt_for(user: User) -> str:
    return str(AccessToken.for_user(user))


class WsAuthTests(TestCase):
    def test_authorization_header(self):
        scope = {
            'headers': [(b'authorization', b'Bearer abc123')],
            'query_string': b'',
            'subprotocols': [],
        }
        token, source = extract_ws_bearer_token(scope)
        self.assertEqual(token, 'abc123')
        self.assertEqual(source, 'authorization')

    def test_subprotocol_bearer(self):
        scope = {
            'headers': [],
            'query_string': b'',
            'subprotocols': [f'{BEARER_SUBPROTOCOL_PREFIX}tok456'.encode()],
        }
        token, source = extract_ws_bearer_token(scope)
        self.assertEqual(token, 'tok456')
        self.assertEqual(source, 'subprotocol')

    @override_settings(DEBUG=False)
    def test_query_token_rejected_in_production(self):
        scope = {
            'headers': [],
            'query_string': b'token=legacy',
            'subprotocols': [],
            'client': ('127.0.0.1', 1234),
        }
        token, source = extract_ws_bearer_token(scope)
        self.assertEqual(token, '')
        self.assertEqual(source, 'none')

    @override_settings(DEBUG=True)
    def test_query_token_deprecated_in_debug(self):
        scope = {
            'headers': [],
            'query_string': b'token=legacy',
            'subprotocols': [],
            'client': ('127.0.0.1', 1234),
        }
        token, source = extract_ws_bearer_token(scope)
        self.assertEqual(token, 'legacy')
        self.assertEqual(source, 'query_deprecated')

    def test_jwt_token_valid_for_user(self):
        user = User.objects.create_user('authcheck', 'auth@test.invalid', 'pwd')
        token = _jwt_for(user)
        scope = {
            'headers': [(b'authorization', f'Bearer {token}'.encode())],
            'query_string': b'',
            'subprotocols': [],
        }
        extracted, source = extract_ws_bearer_token(scope)
        self.assertEqual(extracted, token)
        self.assertEqual(source, 'authorization')


class WsRateLimitTests(TestCase):
    def test_leaderboard_connection_limit(self):
        scope = {'headers': [], 'client': ('10.0.0.1', 5000)}
        for i in range(10):
            self.assertTrue(
                allow_ws_connection(scope, namespace='contest_leaderboard'),
                f'connexion {i + 1} devrait passer',
            )
        self.assertFalse(allow_ws_connection(scope, namespace='contest_leaderboard'))


@override_settings(
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}},
)
class NotificationWsBroadcastTests(TestCase):
    """
    Simule 2 workers Gunicorn/Daphne : deux channel_name distincts dans le même groupe
    reçoivent tous les deux un group_send (broadcast cross-worker).
    """

    def setUp(self):
        self.user = User.objects.create_user('wsuser', 'ws@test.invalid', 'pwd')

    def test_broadcast_to_two_workers(self):
        async def _run():
            layer = get_channel_layer()
            group = notifications_group_name(self.user.id)
            worker_a = 'worker_a!abc123'
            worker_b = 'worker_b!def456'

            await layer.group_add(group, worker_a)
            await layer.group_add(group, worker_b)

            payload = {
                'id': 99,
                'notification_type': 'test',
                'title': 'Hello',
                'message': 'World',
                'is_read': False,
            }
            await layer.group_send(
                group,
                {'type': 'notification.event', 'payload': payload},
            )

            msg_a = await layer.receive(worker_a)
            msg_b = await layer.receive(worker_b)

            self.assertEqual(msg_a['type'], 'notification.event')
            self.assertEqual(msg_b['type'], 'notification.event')
            self.assertEqual(msg_a['payload'], payload)
            self.assertEqual(msg_b['payload'], payload)

            await layer.group_discard(group, worker_a)
            await layer.group_discard(group, worker_b)

        async_to_sync(_run)()
