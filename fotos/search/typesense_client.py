"""Client Typesense — indexation et requêtes."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from django.conf import settings

from .schemas import ALL_SCHEMAS, BOARDS_COLLECTION, FOTOS_COLLECTION, USERS_COLLECTION

logger = logging.getLogger('fotoce.search.typesense')

_client = None


class TypesenseUnavailable(Exception):
    """Typesense injoignable ou mal configuré."""


def typesense_configured() -> bool:
    return bool(getattr(settings, 'TYPESENSE_HOST', '') and getattr(settings, 'TYPESENSE_API_KEY', ''))


def get_typesense_client():
    global _client
    if _client is not None:
        return _client
    if not typesense_configured():
        raise TypesenseUnavailable('Typesense non configuré (TYPESENSE_HOST / TYPESENSE_API_KEY).')
    try:
        import typesense
    except ImportError as exc:
        raise TypesenseUnavailable('Package typesense non installé.') from exc

    raw_host = settings.TYPESENSE_HOST.strip()
    parsed = urlparse(raw_host if '://' in raw_host else f'http://{raw_host}')
    protocol = parsed.scheme or getattr(settings, 'TYPESENSE_PROTOCOL', 'http')
    host = parsed.hostname or 'localhost'
    port = parsed.port or int(getattr(settings, 'TYPESENSE_PORT', 8108))

    _client = typesense.Client(
        {
            'nodes': [{'host': host, 'port': str(port), 'protocol': protocol}],
            'api_key': settings.TYPESENSE_API_KEY,
            'connection_timeout_seconds': float(getattr(settings, 'TYPESENSE_TIMEOUT_SECONDS', 2)),
        }
    )
    return _client


def ensure_collections() -> None:
    client = get_typesense_client()
    existing = {c['name'] for c in client.collections.retrieve()}
    for schema in ALL_SCHEMAS:
        if schema['name'] not in existing:
            client.collections.create(schema)


def upsert_document(collection: str, document: dict) -> None:
    client = get_typesense_client()
    client.collections[collection].documents.upsert(document)


def delete_document(collection: str, doc_id: str) -> None:
    client = get_typesense_client()
    try:
        client.collections[collection].documents[str(doc_id)].delete()
    except Exception as exc:
        if '404' in str(exc):
            return
        raise


def search_collection(
    collection: str,
    query: str,
    *,
    query_by: str,
    filter_by: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    q = (query or '').strip()
    if not q:
        return []
    client = get_typesense_client()
    params: dict[str, Any] = {
        'q': q,
        'query_by': query_by,
        'per_page': max(1, min(int(limit), 250)),
        'prefix': 'true',
    }
    if filter_by:
        params['filter_by'] = filter_by
    result = client.collections[collection].documents.search(params)
    hits = result.get('hits') or []
    return [hit.get('document') or {} for hit in hits]


def search_foto_ids(query: str, *, limit: int, exclude_author_id: int | None = None) -> list[int]:
    filters = ['moderation_hidden:=false', 'visibility:=public']
    if exclude_author_id:
        filters.append(f'author_id:!={exclude_author_id}')
    docs = search_collection(
        FOTOS_COLLECTION,
        query,
        query_by='title,description,author_username,hashtags',
        filter_by=' && '.join(filters),
        limit=limit,
    )
    return [int(d['id']) for d in docs if d.get('id')]


def search_user_ids(query: str, *, limit: int, exclude_user_ids: list[int] | None = None) -> list[int]:
    filters = ['discoverable_profile:=true']
    docs = search_collection(
        USERS_COLLECTION,
        query,
        query_by='username,display_name',
        filter_by=' && '.join(filters),
        limit=limit + len(exclude_user_ids or []),
    )
    excluded = set(exclude_user_ids or [])
    ids: list[int] = []
    for doc in docs:
        uid = int(doc['id'])
        if uid in excluded:
            continue
        ids.append(uid)
        if len(ids) >= limit:
            break
    return ids


def search_board_ids(
    query: str,
    *,
    limit: int,
    viewer_id: int | None,
) -> list[int]:
    if viewer_id:
        filter_by = f'is_private:=false || owner_id:={viewer_id} || collaborator_ids:=[{viewer_id}]'
    else:
        filter_by = 'is_private:=false'
    docs = search_collection(
        BOARDS_COLLECTION,
        query,
        query_by='name,description,owner_username',
        filter_by=filter_by,
        limit=limit,
    )
    return [int(d['id']) for d in docs if d.get('id')]
