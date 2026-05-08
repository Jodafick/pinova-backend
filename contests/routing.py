from django.urls import path

from .consumers import ContestLeaderboardConsumer

websocket_urlpatterns = [
    path('api/contest/leaderboard/events/ws', ContestLeaderboardConsumer.as_asgi()),
]
