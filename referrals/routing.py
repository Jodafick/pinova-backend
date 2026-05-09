from django.urls import path

from .consumers import ReferralLeaderboardConsumer

websocket_urlpatterns = [
    path('api/referrals/leaderboard/ws', ReferralLeaderboardConsumer.as_asgi()),
]
