"""Service des uploads ``MEDIA`` avec en-têtes de cache agressifs (navigateur + clients HTTP)."""

from django.conf import settings
from django.views.static import serve as static_serve


def serve_media(request, path):
    response = static_serve(request, path, document_root=settings.MEDIA_ROOT)
    if response.status_code == 200:
        ctl = getattr(
            settings,
            'MEDIA_CACHE_CONTROL',
            'public, max-age=31536000, immutable',
        )
        response['Cache-Control'] = ctl
    return response
