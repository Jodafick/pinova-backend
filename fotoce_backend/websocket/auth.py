"""Authentification WebSocket — header Authorization (prod) + subprotocol navigateur."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

from django.conf import settings

logger = logging.getLogger('fotoce.ws')

BEARER_SUBPROTOCOL_PREFIX = 'fotoce.bearer.'


def _header_authorization(scope) -> str:
    for key, val in scope.get('headers') or []:
        if key.lower() != b'authorization':
            continue
        raw = val.decode('utf-8', errors='ignore').strip()
        if raw.lower().startswith('bearer '):
            return raw[7:].strip()
    return ''


def _subprotocol_bearer(scope) -> str:
    for proto in scope.get('subprotocols') or []:
        s = proto.decode('utf-8', errors='ignore') if isinstance(proto, bytes) else str(proto)
        if s.startswith(BEARER_SUBPROTOCOL_PREFIX):
            return s[len(BEARER_SUBPROTOCOL_PREFIX) :].strip()
    return ''


def _query_token(scope) -> str:
    query = parse_qs((scope.get('query_string') or b'').decode('utf-8'))
    return str((query.get('token') or [''])[0] or '').strip()


def extract_ws_bearer_token(scope) -> tuple[str, str]:
    """
    Retourne (token, source).
    source : authorization | subprotocol | query_deprecated | none
    En production (?token= interdit), source query_deprecated n'est jamais renvoyée.
    """
    token = _header_authorization(scope)
    if token:
        return token, 'authorization'

    token = _subprotocol_bearer(scope)
    if token:
        return token, 'subprotocol'

    token = _query_token(scope)
    if token:
        if settings.DEBUG:
            logger.warning(
                'WebSocket auth via ?token= est déprécié — utilisez Authorization ou subprotocol %s',
                BEARER_SUBPROTOCOL_PREFIX,
            )
            return token, 'query_deprecated'
        logger.warning('WebSocket ?token= rejeté en production (client=%s)', _client_ip(scope))
    return '', 'none'


def pick_accepted_subprotocol(scope) -> str | None:
    """Subprotocol à renvoyer dans accept() si le client en a proposé un valide."""
    for proto in scope.get('subprotocols') or []:
        s = proto.decode('utf-8', errors='ignore') if isinstance(proto, bytes) else str(proto)
        if s.startswith(BEARER_SUBPROTOCOL_PREFIX):
            return s
    return None


def _client_ip(scope) -> str:
    headers = dict(scope.get('headers') or [])
    forwarded = headers.get(b'x-forwarded-for', b'').decode('utf-8', errors='ignore').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    client = scope.get('client')
    if client and len(client) >= 1:
        return str(client[0])
    return 'unknown'
