from django.urls import path

from ads import manager_views, views

urlpatterns = [
    path('ads/manager/bootstrap/', manager_views.ManagerBootstrapView.as_view(), name='ads-manager-bootstrap'),
    path('ads/manager/campaigns/', manager_views.ManagerCampaignCreateView.as_view(), name='ads-manager-campaigns'),
    path('ads/manager/creatives/', manager_views.ManagerCreativeCreateView.as_view(), name='ads-manager-creatives'),
    path('ads/manager/ads/', manager_views.ManagerAdCreateView.as_view(), name='ads-manager-ads'),
    path('ads/delivery/candidates/', views.NativeCandidatesView.as_view(), name='ads-delivery-candidates'),
    path('ads/events/batch/', views.PendingEventsBatchView.as_view(), name='ads-events-batch'),
    path('ads/geo/autocomplete/', views.GeoAutocompleteView.as_view(), name='ads-geo-autocomplete'),
    path('ads/geo/reverse/', views.GeoReverseView.as_view(), name='ads-geo-reverse'),
    path('ads/interactions/hide/', views.AdHideView.as_view(), name='ads-interactions-hide'),
    path('ads/interactions/report/', views.AdReportView.as_view(), name='ads-interactions-report'),
    path('ads/<uuid:ad_id>/', views.AdDetailPublicView.as_view(), name='ads-detail'),
]
