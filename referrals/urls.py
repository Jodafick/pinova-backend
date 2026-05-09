from django.urls import path

from .referral_contest_views import (
    ReferralContestArchivesView,
    ReferralContestCurrentView,
    ReferralContestHistoryView,
    ReferralLeaderboardEventsPollView,
)
from .views import (
    ReferralIntentView,
    ReferralLeaderboardView,
    ReferralMeView,
    ReferralMyRefereesView,
    ReferralResolveView,
    ReferralUniversalRedirectView,
)

urlpatterns = [
    path('referrals/intent/', ReferralIntentView.as_view(), name='referrals-intent'),
    path('referrals/resolve/<str:code>/', ReferralResolveView.as_view(), name='referrals-resolve'),
    path('referrals/me/', ReferralMeView.as_view(), name='referrals-me'),
    path('referrals/my-referees/', ReferralMyRefereesView.as_view(), name='referrals-my-referees'),
    path('referrals/leaderboard/', ReferralLeaderboardView.as_view(), name='referrals-leaderboard'),
    path('referrals/leaderboard/events/', ReferralLeaderboardEventsPollView.as_view(), name='referrals-leaderboard-events'),
    path('referrals/contest/current/', ReferralContestCurrentView.as_view(), name='referrals-contest-current'),
    path('referrals/contest/archives/', ReferralContestArchivesView.as_view(), name='referrals-contest-archives'),
    path('referrals/contest/history/<str:contest_key>/', ReferralContestHistoryView.as_view(), name='referrals-contest-history'),
    path('r/<str:code>/', ReferralUniversalRedirectView.as_view(), name='referrals-universal-redirect'),
]
