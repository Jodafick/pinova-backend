from django.urls import path

from .consumers import NotificationConsumer

websocket_urlpatterns = [
    path('api/notifications/ws', NotificationConsumer.as_asgi()),
]
