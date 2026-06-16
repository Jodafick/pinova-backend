from django.urls import path

from .views import (
    ContestArchiveIndexView,
    ContestHistoryView,
    CurrentContestView,
    LeaderboardCreatorsView,
    LeaderboardEventsView,
    LeaderboardFotosView,
)

urlpatterns = [
    path('contest/current', CurrentContestView.as_view(), name='contest-current'),
    path('contest/archives', ContestArchiveIndexView.as_view(), name='contest-archives'),
    path('contest/leaderboard/fotos', LeaderboardFotosView.as_view(), name='contest-leaderboard-fotos'),
    path('contest/leaderboard/creators', LeaderboardCreatorsView.as_view(), name='contest-leaderboard-creators'),
    path('contest/leaderboard/events', LeaderboardEventsView.as_view(), name='contest-leaderboard-events'),
    path('contest/history/<str:contest_key>', ContestHistoryView.as_view(), name='contest-history'),
]
