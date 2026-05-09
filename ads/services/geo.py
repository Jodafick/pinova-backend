"""
Géolocalisation : Mapbox Geocoding v5 (autocomplete, forward, reverse).
Variable d’environnement : ``MAPBOX_ACCESS_TOKEN``. Alternative : ``GOOGLE_MAPS_API_KEY``.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from django.conf import settings


def _mapbox_token() -> str:
    return (getattr(settings, 'MAPBOX_ACCESS_TOKEN', None) or os.environ.get('MAPBOX_ACCESS_TOKEN', '') or '').strip()


def mapbox_geocode_forward(query: str, *, limit: int = 6, country: str | None = None) -> list[dict[str, Any]]:
    token = _mapbox_token()
    if not token or not query.strip():
        return []
    q = requests.utils.quote(query.strip())
    cc = f"&country={country}" if country else ''
    url = f'https://api.mapbox.com/geocoding/v5/mapbox.places/{q}.json?access_token={token}&limit={limit}{cc}'
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    data = r.json()
    out = []
    for feat in data.get('features', [])[:limit]:
        ctx = feat.get('context', [])
        place_type = (feat.get('place_type') or ['place'])[0]
        out.append(
            {
                'label': feat.get('place_name') or feat.get('text'),
                'provider': 'mapbox',
                'provider_place_id': feat.get('id'),
                'place_type': place_type,
                'center': feat.get('center'),
                'bbox': feat.get('bbox'),
                'structured': _structure_mapbox_feature(feat, ctx),
            }
        )
    return out


def _structure_mapbox_feature(feat: dict, context: list) -> dict[str, Any]:
    country_code = ''
    region = ''
    locality = feat.get('text') or ''
    for c in context:
        cid = c.get('id') or ''
        if cid.startswith('country'):
            country_code = (c.get('short_code') or '').upper()
        elif cid.startswith('region'):
            region = c.get('text') or ''
    center = feat.get('center') or [None, None]
    return {
        'label': feat.get('place_name'),
        'locality': locality,
        'region': region,
        'country_code': country_code,
        'lat': center[1],
        'lng': center[0],
    }


def mapbox_reverse_geocode(lng: float, lat: float) -> dict[str, Any] | None:
    token = _mapbox_token()
    if not token:
        return None
    url = f'https://api.mapbox.com/geocoding/v5/mapbox.places/{lng},{lat}.json?access_token={token}&limit=1'
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    feats = r.json().get('features') or []
    if not feats:
        return None
    feat = feats[0]
    return _structure_mapbox_feature(feat, feat.get('context', []))
