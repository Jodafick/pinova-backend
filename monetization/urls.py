from django.urls import path

from .tip_views import TipCheckoutView, TipConfigView, TipWalletView, TipWithdrawView
from .stats_views import CheckoutPendingRecapView, PublicMonetizationStatsView
from .views import (
    BoostPackageListView,
    BoostReachEstimateView,
    CampaignTargetingOptionsView,
    ContextualAdView,
    MyFotoBoostsView,
    NetworkAdConfigView,
    PartnerCampaignClickView,
    PartnerCampaignDetailView,
    PartnerCampaignListCreateView,
    FotoBoostCheckoutView,
    FotoPromoCampaignClickView,
    FotoPromoCampaignDetailView,
    FotoPromoCampaignListCreateView,
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
    path('monetization/fotos/<slug:foto_slug>/boost-estimate/', BoostReachEstimateView.as_view()),
    path('monetization/fotos/<slug:foto_slug>/boost/', FotoBoostCheckoutView.as_view()),
    path('monetization/my-boosts/', MyFotoBoostsView.as_view()),
    path('monetization/contextual-ad/', ContextualAdView.as_view()),
    path('monetization/network-ad-config/', NetworkAdConfigView.as_view()),
    path('monetization/campaign-targeting-options/', CampaignTargetingOptionsView.as_view()),
    path('monetization/foto-promo-campaigns/', FotoPromoCampaignListCreateView.as_view()),
    path('monetization/foto-promo-campaigns/<int:campaign_id>/', FotoPromoCampaignDetailView.as_view()),
    path('monetization/foto-promo-campaigns/<int:campaign_id>/click/', FotoPromoCampaignClickView.as_view()),
]
