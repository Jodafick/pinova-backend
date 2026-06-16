"""
URL configuration for fotoce_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from fotoce_backend.media_serving.views import serve_media
from fotoce_backend.health.views import celery_health, health, health_ready, home

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('api/health/', health, name='health'),
    path('api/health/ready/', health_ready, name='health-ready'),
    path('api/health/celery/', celery_health, name='health-celery'),
    path('api/', include('fotos.urls')),
    path('api/', include('accounts.urls')),
    path('api/', include('contests.urls')),
    path('api/', include('referrals.urls')),
    path('api/', include('monetization.urls')),
    path('api/notifications/', include('notifications.urls')),
    # Médias : accès contrôlé par MediaAccessMiddleware (signatures HMAC + fotos.visibility).
    # Ne pas exposer MEDIA_ROOT / bucket S3 en direct sans les mêmes contrôles.
    re_path(r'^media/(?P<path>.*)$', serve_media),
]
