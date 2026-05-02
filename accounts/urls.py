from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProfileViewSet,
    UserViewSet,
    RegisterView,
    UserMeView,
    ProfileShareTokenView,
    GoogleLogin,
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
    SupportTicketView,
)

router = DefaultRouter()
router.register(r'profiles', ProfileViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('me/', UserMeView.as_view(), name='user-me'),
    path('me/profile-share-token/', ProfileShareTokenView.as_view(), name='profile-share-token'),
    path('subscription/pricing/', SubscriptionPricingView.as_view(), name='subscription-pricing'),
    path('subscription/trial/start/', SubscriptionTrialStartView.as_view(), name='subscription-trial-start'),
    path('subscription/invoices/', SubscriptionInvoiceListView.as_view(), name='subscription-invoices'),
    path('subscription/currencies/', CurrencyOptionsView.as_view(), name='subscription-currencies'),
    path('subscription/checkout/', SubscriptionCheckoutView.as_view(), name='subscription-checkout'),
    path('subscription/confirm/', SubscriptionConfirmView.as_view(), name='subscription-confirm'),
    path('subscription/manage/', SubscriptionManageView.as_view(), name='subscription-manage'),
    path('subscription/webhook/fedapay/', SubscriptionWebhookView.as_view(), name='subscription-webhook-fedapay'),
    path('support/tickets/', SupportTicketView.as_view(), name='support-tickets'),
    
    # Auth endpoints
    path('auth/', include('dj_rest_auth.urls')),
    path('auth/registration/', include('dj_rest_auth.registration.urls')),
    path('auth/social/google/', GoogleLogin.as_view(), name='google_login'),
    path('auth/social/facebook/', FacebookLogin.as_view(), name='facebook_login'),
    path('auth/social/', include('allauth.socialaccount.urls')),
]
