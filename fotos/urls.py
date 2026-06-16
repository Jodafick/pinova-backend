from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FotoViewSet,
    BoardViewSet,
    BoardCollaborationInviteViewSet,
    legal_document_detail,
    faq_overview,
)

router = DefaultRouter()
router.register(r'fotos', FotoViewSet)
router.register(r'pins', FotoViewSet, basename='pins')
router.register(r'boards', BoardViewSet, basename='boards')
router.register(r'board-invitations', BoardCollaborationInviteViewSet, basename='board-invitations')

urlpatterns = [
    path('faq/', faq_overview),
    path('legal/<slug>/', legal_document_detail),
    path('feed/recommendations', FotoViewSet.as_view({'get': 'recommendations'})),
    path('', include(router.urls)),
]
