from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PinViewSet,
    BoardViewSet,
    BoardCollaborationInviteViewSet,
    legal_document_detail,
    faq_overview,
)
from .sync_views import SyncView

router = DefaultRouter()
router.register(r'pins', PinViewSet)
router.register(r'boards', BoardViewSet, basename='boards')
router.register(r'board-invitations', BoardCollaborationInviteViewSet, basename='board-invitations')

urlpatterns = [
    path('faq/', faq_overview),
    path('legal/<slug>/', legal_document_detail),
    path('sync/', SyncView.as_view()),
    path('feed/recommendations', PinViewSet.as_view({'get': 'recommendations'})),
    path('', include(router.urls)),
]
