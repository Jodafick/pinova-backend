"""
ASGI config for fotoce_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fotoce_backend.settings')

django_asgi_app = get_asgi_application()

from contests.routing import websocket_urlpatterns as contest_ws
from notifications.routing import websocket_urlpatterns as notification_ws
from referrals.routing import websocket_urlpatterns as referral_ws

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': URLRouter(contest_ws + referral_ws + notification_ws),
    }
)
