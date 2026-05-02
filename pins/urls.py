from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PinViewSet, BoardViewSet, BoardCollaborationInviteViewSet, legal_document_detail

router = DefaultRouter()
router.register(r'pins', PinViewSet)
router.register(r'boards', BoardViewSet, basename='boards')
router.register(r'board-invitations', BoardCollaborationInviteViewSet, basename='board-invitations')

urlpatterns = [
    path('legal/<slug>/', legal_document_detail),
    path('', include(router.urls)),
]
