from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProfileViewSet,
    UserBlockViewSet,
    UserViewSet,
    RegisterView,
    UserMeView,
    SetInitialPasswordView,
    ProfileShareTokenView,
    AccountDeletionRequestView,
    AccountDeletionCancelView,
    GoogleLogin,
    MobileGoogleSessionExchangeView,
    MobileGoogleSessionStartView,
    FacebookLogin,
    VerifyOTPView,
    ResendOTPView,
    SubscriptionCheckoutView,
    SubscriptionConfirmView,
    SubscriptionPricingView,
    CurrencyOptionsView,
    SubscriptionManageView,
    SubscriptionWebhookView,
    SubscriptionTrialStartView,
    SubscriptionInvoiceListView,
    SubscriptionInvoiceReceiptView,
    SupportTicketView,
)
from .reference_views import ReferenceInterestsView
from .subscription_seat_views import (
    SubscriptionSeatAdminRevokeHubView,
    SubscriptionSeatInviteCreateView,
    SubscriptionSeatInviteDetailView,
    SubscriptionSeatLeaveView,
    SubscriptionSeatMemberRemoveView,
    SubscriptionSeatsOverviewView,
)

router = DefaultRouter()
router.register(r'profiles', ProfileViewSet)
router.register(r'users', UserViewSet)
router.register(r'blocks', UserBlockViewSet, basename='userblock')

urlpatterns = [
    path('', include(router.urls)),
    path('reference/interests/', ReferenceInterestsView.as_view(), name='reference-interests'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('me/', UserMeView.as_view(), name='user-me'),
    path('me/set-password/', SetInitialPasswordView.as_view(), name='user-me-set-password'),
    path('me/profile-share-token/', ProfileShareTokenView.as_view(), name='profile-share-token'),
    path('me/account-deletion/request/', AccountDeletionRequestView.as_view(), name='account-deletion-request'),
    path('me/account-deletion/cancel/', AccountDeletionCancelView.as_view(), name='account-deletion-cancel'),
    path('subscription/pricing/', SubscriptionPricingView.as_view(), name='subscription-pricing'),
    path('subscription/trial/start/', SubscriptionTrialStartView.as_view(), name='subscription-trial-start'),
    path('subscription/invoices/', SubscriptionInvoiceListView.as_view(), name='subscription-invoices'),
    path(
        'subscription/invoices/<int:invoice_id>/receipt/',
        SubscriptionInvoiceReceiptView.as_view(),
        name='subscription-invoice-receipt',
    ),
    path('subscription/currencies/', CurrencyOptionsView.as_view(), name='subscription-currencies'),
    path('subscription/checkout/', SubscriptionCheckoutView.as_view(), name='subscription-checkout'),
    path('subscription/confirm/', SubscriptionConfirmView.as_view(), name='subscription-confirm'),
    path('subscription/manage/', SubscriptionManageView.as_view(), name='subscription-manage'),
    path('subscription/webhook/fedapay/', SubscriptionWebhookView.as_view(), name='subscription-webhook-fedapay'),
    path('subscription/seats/', SubscriptionSeatsOverviewView.as_view(), name='subscription-seats'),
    path('subscription/seats/invites/', SubscriptionSeatInviteCreateView.as_view(), name='subscription-seat-invites'),
    path(
        'subscription/seats/invites/<uuid:invite_id>/',
        SubscriptionSeatInviteDetailView.as_view(),
        name='subscription-seat-invite-detail',
    ),
    path(
        'subscription/seats/members/<str:username>/',
        SubscriptionSeatMemberRemoveView.as_view(),
        name='subscription-seat-member-remove',
    ),
    path('subscription/seats/leave/', SubscriptionSeatLeaveView.as_view(), name='subscription-seat-leave'),
    path(
        'subscription/seats/revoke-all/',
        SubscriptionSeatAdminRevokeHubView.as_view(),
        name='subscription-seat-revoke-all',
    ),
    path('support/tickets/', SupportTicketView.as_view(), name='support-tickets'),
    
    # Auth endpoints
    path('auth/', include('dj_rest_auth.urls')),
    path('auth/registration/', include('dj_rest_auth.registration.urls')),
    path('auth/social/google/', GoogleLogin.as_view(), name='google_login'),
    path('auth/mobile/google/session/', MobileGoogleSessionStartView.as_view(), name='mobile_google_session_start'),
    path('auth/mobile/google/exchange/', MobileGoogleSessionExchangeView.as_view(), name='mobile_google_session_exchange'),
    path('auth/social/facebook/', FacebookLogin.as_view(), name='facebook_login'),
    path('auth/social/', include('allauth.socialaccount.urls')),
]
