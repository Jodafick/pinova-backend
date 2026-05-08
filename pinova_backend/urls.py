"""
URL configuration for pinova_backend project.

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

from .media_views import serve_media

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('pins.urls')),
    path('api/', include('accounts.urls')),
    path('api/', include('contests.urls')),
    path('api/notifications/', include('notifications.urls')),
    # Médias utilisateurs : Cache-Control long (+ version cv= côté serializers).
    # En production, si nginx sert /media/ directement, aligner les mêmes en-têtes là-bas.
    re_path(r'^media/(?P<path>.*)$', serve_media),
]
