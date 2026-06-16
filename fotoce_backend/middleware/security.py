"""Middleware en-têtes de sécurité (CSP basique)."""

from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """Ajoute une CSP minimale sur les réponses HTTP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(settings, 'CONTENT_SECURITY_POLICY', None):
            response['Content-Security-Policy'] = settings.CONTENT_SECURITY_POLICY
        return response
