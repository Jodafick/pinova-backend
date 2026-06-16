"""Service sécurisé des uploads ``MEDIA`` (post-middleware ``MediaAccessMiddleware``)."""

import mimetypes
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.views.static import serve as static_serve

from fotoce_backend.media_serving.access import evaluate_media_access, safe_join_media_root


def _cache_control_for_reason(reason: str) -> str:
    if reason == 'public':
        return getattr(
            settings,
            'MEDIA_CACHE_CONTROL',
            'public, max-age=31536000, immutable',
        )
    return getattr(
        settings,
        'MEDIA_SIGNED_CACHE_CONTROL',
        'private, max-age=3600',
    )


def serve_media(request, path):
    if not getattr(request, 'fotoce_media_access_granted', False):
        allowed, reason, _resource = evaluate_media_access(request, path)
        if not allowed:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        request.fotoce_media_access_granted = True
        request.fotoce_media_access_reason = reason

    reason = getattr(request, 'fotoce_media_access_reason', 'public')
    ctl = _cache_control_for_reason(reason)

    use_remote = getattr(settings, 'USE_S3_MEDIA', False) or getattr(settings, 'USE_CLOUDINARY_MEDIA', False)
    if use_remote:
        if not default_storage.exists(path):
            raise Http404('Media not found')
        content_type, _encoding = mimetypes.guess_type(path)
        file_handle = default_storage.open(path, 'rb')
        response = FileResponse(file_handle, content_type=content_type or 'application/octet-stream')
        response['Cache-Control'] = ctl
        return response

    try:
        safe_join_media_root(path)
    except ValueError:
        return HttpResponseForbidden()

    response = static_serve(request, path, document_root=settings.MEDIA_ROOT)
    if response.status_code == 200:
        response['Cache-Control'] = ctl
    return response
