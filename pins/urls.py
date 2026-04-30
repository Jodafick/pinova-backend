from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PinViewSet, BoardViewSet

router = DefaultRouter()
router.register(r'pins', PinViewSet)
router.register(r'boards', BoardViewSet, basename='boards')

urlpatterns = [
    path('', include(router.urls)),
]
