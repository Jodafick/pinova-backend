"""Bloque l'accès IDOR à ``/media/`` — vérifie signature et ``fotos.visibility``."""

from django.http import JsonResponse

from fotoce_backend.media_serving.access import evaluate_media_access


class MediaAccessMiddleware:
    """
    Intercepte ``/media/`` avant la vue statique.
    Pins publics : accès direct ; fotos privés / stories / avatars privés : URL signée HMAC.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ''
        media_prefix = '/media/'
        if not path.startswith(media_prefix):
            return self.get_response(request)

        relative = path[len(media_prefix):]
        allowed, reason, _resource = evaluate_media_access(request, relative)
        if not allowed:
            if reason in ('signed_invalid', 'unknown', 'path_invalid'):
                return JsonResponse({'error': 'Forbidden'}, status=403)
            return JsonResponse({'error': 'Forbidden'}, status=403)

        request.fotoce_media_access_granted = True
        request.fotoce_media_access_reason = reason
        return self.get_response(request)
