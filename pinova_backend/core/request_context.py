"""Contexte requête (request_id, user_id) — corrélation logs / Sentry."""
from __future__ import annotations

import contextvars

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('request_id', default=None)
user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar('user_id', default=None)


def set_request_context(*, request_id: str | None = None, user_id: int | None = None) -> None:
    if request_id is not None:
        request_id_var.set(request_id)
    if user_id is not None:
        user_id_var.set(user_id)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_user_id() -> int | None:
    return user_id_var.get()


def clear_request_context() -> None:
    request_id_var.set(None)
    user_id_var.set(None)
