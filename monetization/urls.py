from django.urls import path

from .tip_views import TipCheckoutView, TipConfigView, TipWalletView, TipWithdrawView
from .stats_views import CheckoutPendingRecapView, PublicMonetizationStatsView
from .views import (
    BoostPackageListView,
    BoostReachEstimateView,
    CampaignTargetingOptionsView,
    ContextualAdView,
    MyPinBoostsView,
    NetworkAdConfigView,
    PartnerCampaignClickView,
    PartnerCampaignDetailView,
    PartnerCampaignListCreateView,
    PinBoostCheckoutView,
    PinPromoCampaignClickView,
    PinPromoCampaignDetailView,
    PinPromoCampaignListCreateView,
)

urlpatterns = [
    path('monetization/stats/public/', PublicMonetizationStatsView.as_view()),
    path('monetization/checkout/pending-recap/', CheckoutPendingRecapView.as_view()),
    path('monetization/tips/config/', TipConfigView.as_view()),
    path('monetization/tips/wallet/', TipWalletView.as_view()),
    path('monetization/tips/checkout/', TipCheckoutView.as_view()),
    path('monetization/tips/withdraw/', TipWithdrawView.as_view()),
    path('monetization/partner-campaigns/', PartnerCampaignListCreateView.as_view()),
    path('monetization/partner-campaigns/<int:campaign_id>/', PartnerCampaignDetailView.as_view()),
    path('monetization/partner-campaigns/<int:campaign_id>/click/', PartnerCampaignClickView.as_view()),
    path('monetization/boost-packages/', BoostPackageListView.as_view()),
    path('monetization/pins/<slug:pin_slug>/boost-estimate/', BoostReachEstimateView.as_view()),
    path('monetization/pins/<slug:pin_slug>/boost/', PinBoostCheckoutView.as_view()),
    path('monetization/my-boosts/', MyPinBoostsView.as_view()),
    path('monetization/contextual-ad/', ContextualAdView.as_view()),
    path('monetization/network-ad-config/', NetworkAdConfigView.as_view()),
    path('monetization/campaign-targeting-options/', CampaignTargetingOptionsView.as_view()),
    path('monetization/pin-promo-campaigns/', PinPromoCampaignListCreateView.as_view()),
    path('monetization/pin-promo-campaigns/<int:campaign_id>/', PinPromoCampaignDetailView.as_view()),
    path('monetization/pin-promo-campaigns/<int:campaign_id>/click/', PinPromoCampaignClickView.as_view()),
]
