"""
Données paginées pour GET/PATCH `me/` : 1ère page tableaux + pins créés + enregistrés.
Réutilise les ViewSet pour les filtres (visibilité, saves, etc.).
Les entités sont sérialisées avec la vraie `request` client pour des URL médias correctes.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from pins.serializers import BoardSerializer, PinSerializer
from pins.views import BoardViewSet, PinViewSet

ME_BOARDS_PAGE_SIZE = 24
ME_PINS_PAGE_SIZE = 24


def _meta_from_request(request: Request) -> dict:
    host = request.get_host() or 'localhost'
    scheme = 'https' if request.is_secure() else 'http'
    return {
        'HTTP_HOST': host,
        'wsgi.url_scheme': scheme,
        'SERVER_NAME': host.split(':')[0],
    }


def _factory_get(query: dict, request: Request) -> Request:
    factory = APIRequestFactory()
    wsgi_req = factory.get('/_', query, **_meta_from_request(request))
    force_authenticate(wsgi_req, user=request.user)
    return Request(wsgi_req)


def _pins_page_bundle(
    main_request: Request,
    *,
    queryset_factory,
    next_query: dict | None,
) -> dict:
    qs = queryset_factory()
    total = qs.count()
    chunk = list(qs[:ME_PINS_PAGE_SIZE])
    ser = PinSerializer(chunk, many=True, context={'request': main_request})
    next_url = None
    if total > ME_PINS_PAGE_SIZE and next_query:
        path = reverse('pin-list')
        q = dict(next_query)
        q['page'] = 2
        q['page_size'] = ME_PINS_PAGE_SIZE
        next_url = main_request.build_absolute_uri(f'{path}?{urlencode(q)}')
    return {
        'count': total,
        'next': next_url,
        'previous': None,
        'results': ser.data,
    }


def _boards_page_bundle(main_request: Request, *, queryset_factory) -> dict:
    qs = queryset_factory()
    total = qs.count()
    chunk = list(qs[:ME_BOARDS_PAGE_SIZE])
    ser = BoardSerializer(chunk, many=True, context={'request': main_request})
    next_url = None
    if total > ME_BOARDS_PAGE_SIZE:
        path = reverse('boards-list')
        q = urlencode({'page': 2, 'page_size': ME_BOARDS_PAGE_SIZE})
        next_url = main_request.build_absolute_uri(f'{path}?{q}')
    return {
        'count': total,
        'next': next_url,
        'previous': None,
        'results': ser.data,
    }


def build_me_hydration_bundle(request: Request) -> dict:
    """À fusionner dans la réponse JSON du propriétaire connecté (`me/`)."""
    user = request.user
    if not user.is_authenticated:
        return {}

    req_created = _factory_get(
        {'author': user.username, 'page': '1', 'page_size': str(ME_PINS_PAGE_SIZE)},
        request,
    )
    vw_c = PinViewSet()
    vw_c.request = req_created
    vw_c.action = 'list'
    vw_c.kwargs = {}
    created = _pins_page_bundle(
        request,
        queryset_factory=lambda: vw_c.get_queryset(),
        next_query={'author': user.username, 'page_size': ME_PINS_PAGE_SIZE},
    )

    req_saved = _factory_get(
        {'saved_by_me': '1', 'page': '1', 'page_size': str(ME_PINS_PAGE_SIZE)},
        request,
    )
    vw_s = PinViewSet()
    vw_s.request = req_saved
    vw_s.action = 'list'
    vw_s.kwargs = {}
    saved = _pins_page_bundle(
        request,
        queryset_factory=lambda: vw_s.get_queryset(),
        next_query={'saved_by_me': '1', 'page_size': ME_PINS_PAGE_SIZE},
    )

    req_b = _factory_get({'page': '1', 'page_size': str(ME_BOARDS_PAGE_SIZE)}, request)
    vb = BoardViewSet()
    vb.request = req_b
    vb.action = 'list'
    vb.kwargs = {}
    boards = _boards_page_bundle(request, queryset_factory=lambda: vb.get_queryset())

    return {
        'me_boards_page': boards,
        'me_created_pins_page': created,
        'me_saved_pins_page': saved,
    }
