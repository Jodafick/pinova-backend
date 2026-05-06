"""
Versionnement léger des URLs médias (?cv=<token>) pour combiner :

- Cache-Control long côté serveur (immutable) : la ressource ne change pas tant que l’URL ne change pas.
- Invalidation automatique lorsque le fichier sous MEDIA_ROOT change (mtime + taille).

Ne pas ajouter plusieurs clés cv : une seule requête = une entrée cache navigateur / expo-image disk.
"""

from __future__ import annotations

import hashlib
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings


def _safe_join_under_media_root(relative: str) -> str:
    rel = (relative or '').replace('\\', '/').lstrip('/')
    return os.path.normpath(os.path.join(settings.MEDIA_ROOT, rel))


def version_token_for_fieldfile(field_file) -> str | None:
    """Token stable pour une ``FieldFile`` (ImageField/FileField Django)."""
    if not field_file or not getattr(field_file, 'name', None):
        return None
    name = field_file.name
    try:
        path = field_file.path
        st = os.stat(path)
        key = f"{int(st.st_mtime_ns)}:{st.st_size}:{name}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]
    except (NotImplementedError, OSError, AttributeError, ValueError, TypeError):
        return hashlib.sha256(str(name).encode()).hexdigest()[:12]


def version_token_for_relative_media_path(relative_under_media: str) -> str | None:
    """Token à partir d’un chemin sous ``MEDIA_ROOT`` (sans slash initial)."""
    if not relative_under_media:
        return None
    rel = relative_under_media.replace('\\', '/').lstrip('/')
    try:
        full = _safe_join_under_media_root(rel)
        st = os.stat(full)
        key = f"{int(st.st_mtime_ns)}:{st.st_size}:{rel}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]
    except (OSError, TypeError, ValueError):
        return hashlib.sha256(rel.encode()).hexdigest()[:12]


def append_cache_version(absolute_url: str, token: str | None) -> str:
    if not absolute_url or not token:
        return absolute_url or ''
    parts = urlparse(absolute_url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'cv']
    q.append(('cv', token))
    new_query = urlencode(q)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


def build_versioned_media_url(request, field_file) -> str:
    """URL absolue + ``cv`` pour un fichier Django sur disque."""
    if not request or not field_file or not getattr(field_file, 'name', None):
        return ''
    base = request.build_absolute_uri(field_file.url)
    return append_cache_version(base, version_token_for_fieldfile(field_file))


def append_version_using_media_path(absolute_url: str, *, relative_under_media: str | None) -> str:
    """À utiliser lorsqu’on n’a pas de FieldFile (ex.: résultats ``.values()``)."""
    if not absolute_url:
        return ''
    tok = version_token_for_relative_media_path(relative_under_media or '')
    return append_cache_version(absolute_url, tok)
