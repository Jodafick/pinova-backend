from django.urls import path

from .views import (
    BoostPackageListView,
    PartnerCampaignClickView,
    PartnerCampaignDetailView,
    PartnerCampaignListCreateView,
    PinBoostCheckoutView,
)

urlpatterns = [
    path('monetization/partner-campaigns/', PartnerCampaignListCreateView.as_view()),
    path('monetization/partner-campaigns/<int:campaign_id>/', PartnerCampaignDetailView.as_view()),
    path('monetization/partner-campaigns/<int:campaign_id>/click/', PartnerCampaignClickView.as_view()),
    path('monetization/boost-packages/', BoostPackageListView.as_view()),
    path('monetization/pins/<slug:pin_slug>/boost/', PinBoostCheckoutView.as_view()),
]
