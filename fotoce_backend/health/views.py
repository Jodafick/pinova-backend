"""Health checks — DB, Redis, Celery, FedaPay + readiness k8s/Render."""
from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def _check_db() -> dict:
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {'ok': True, 'detail': 'ok', 'latency_ms': latency_ms}
    except Exception as exc:
        return {'ok': False, 'detail': str(exc)[:200], 'latency_ms': None}


def _check_redis() -> dict:
    if not getattr(settings, 'PINNOVA_SHARED_CACHE', False):
        return {'ok': True, 'detail': 'skipped', 'latency_ms': None}
    started = time.perf_counter()
    try:
        cache.set('fotoce_health_ping', '1', timeout=10)
        if cache.get('fotoce_health_ping') != '1':
            return {'ok': False, 'detail': 'read_mismatch', 'latency_ms': None}
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {'ok': True, 'detail': 'ok', 'latency_ms': latency_ms}
    except Exception as exc:
        return {'ok': False, 'detail': str(exc)[:200], 'latency_ms': None}


def _broker_ping() -> tuple[bool, str]:
    try:
        from fotoce_backend.celery import app

        conn = app.connection()
        conn.ensure_connection(max_retries=1, timeout=2.0)
        conn.release()
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)[:200]


def _workers_ping() -> tuple[bool, str, int]:
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        return True, 'eager', 0
    try:
        from fotoce_backend.celery import app

        inspect = app.control.inspect(timeout=2.0)
        ping = inspect.ping() or {}
        count = len(ping)
        if count > 0:
            return True, 'ok', count
        return False, 'no_workers', 0
    except Exception as exc:
        return False, str(exc)[:200], 0


def _check_celery() -> dict:
    broker_ok, broker_detail = _broker_ping()
    workers_ok, workers_detail, worker_count = _workers_ping()
    from fotoce_backend.celery import app

    beat_keys = sorted((app.conf.beat_schedule or {}).keys())
    return {
        'ok': broker_ok,
        'broker': {'ok': broker_ok, 'detail': broker_detail},
        'workers': {
            'ok': workers_ok,
            'detail': workers_detail,
            'count': worker_count,
        },
        'always_eager': bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)),
        'beat_schedule': beat_keys,
    }


def _check_fedapay() -> dict:
    from monetization.fedapay_client import fedapay_health_ping

    ok, detail, latency_ms = fedapay_health_ping()
    return {'ok': ok, 'detail': detail, 'latency_ms': latency_ms}


def _collect_checks() -> dict:
    return {
        'db': _check_db(),
        'redis': _check_redis(),
        'celery': _check_celery(),
        'fedapay': _check_fedapay(),
    }


def _overall_status(checks: dict) -> str:
    critical = [checks['db']['ok'], checks['celery']['broker']['ok']]
    if checks['redis']['detail'] != 'skipped':
        critical.append(checks['redis']['ok'])
    if all(critical):
        optional_ok = checks['fedapay']['ok'] and checks['celery']['workers']['ok']
        return 'ok' if optional_ok else 'degraded'
    return 'degraded'


def _is_ready(checks: dict) -> bool:
    if not checks['db']['ok']:
        return False
    if checks['redis']['detail'] != 'skipped' and not checks['redis']['ok']:
        return False
    if not checks['celery']['broker']['ok']:
        return False
    return True


def _health_body(checks: dict) -> dict:
    return {
        'status': _overall_status(checks),
        'checks': checks,
    }


def _wants_json(request: HttpRequest) -> bool:
    accept = (request.headers.get('Accept') or '').lower()
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    if request.GET.get('format') == 'json':
        return True
    return False


def _home_payload() -> dict:
    release = (getattr(settings, 'SENTRY_RELEASE', '') or '').strip()
    return {
        'service': 'fotoce-api',
        'status': 'ok',
        'release': release or None,
        'environment': getattr(settings, 'SENTRY_ENVIRONMENT', None),
        'endpoints': {
            'health': '/api/health/',
            'ready': '/api/health/ready/',
            'api': '/api/',
            'admin': '/admin/',
        },
    }


def _infra_status_rows(checks: dict) -> list[dict]:
    rows = [
        {
            'label': 'PostgreSQL',
            'state': 'ok' if checks['db']['ok'] else 'off',
            'latency': checks['db'].get('latency_ms'),
        },
    ]
    redis = checks['redis']
    if redis.get('detail') == 'skipped':
        rows.append({'label': 'Redis', 'state': 'skip', 'latency': None})
    else:
        rows.append({
            'label': 'Redis',
            'state': 'ok' if redis['ok'] else 'off',
            'latency': redis.get('latency_ms'),
        })
    broker = checks['celery']['broker']
    rows.append({
        'label': 'Celery broker',
        'state': 'ok' if broker['ok'] else 'off',
        'latency': None,
    })
    return rows


def _home_endpoints() -> list[dict]:
    return [
        {
            'label': 'Santé',
            'title': 'Health check',
            'path': '/api/health/',
            'url': '/api/health/',
        },
        {
            'label': 'Déploiement',
            'title': 'Readiness probe',
            'path': '/api/health/ready/',
            'url': '/api/health/ready/',
        },
        {
            'label': 'REST',
            'title': 'API v1',
            'path': '/api/',
            'url': '/api/',
        },
        {
            'label': 'Admin',
            'title': 'Django Admin',
            'path': '/admin/',
            'url': '/admin/',
        },
    ]


@require_GET
def home(request):
    """
    GET /
    Racine API — page HTML stylée pour les humains, JSON pour les sondes (`Accept: application/json`).
    """
    if _wants_json(request):
        return JsonResponse(_home_payload())

    checks = _collect_checks()
    overall = _overall_status(checks)
    status_class = 'warn' if overall == 'degraded' else 'bad' if not checks['db']['ok'] else ''
    status_label = {
        'ok': 'Tous les systèmes opérationnels',
        'degraded': 'Service dégradé — vérifiez /api/health/',
    }.get(overall, 'Indisponible')

    return render(
        request,
        'home.html',
        {
            'status_class': status_class,
            'status_label': status_label,
            'infra_status': _infra_status_rows(checks),
            'endpoints': _home_endpoints(),
            'release': (getattr(settings, 'SENTRY_RELEASE', '') or '').strip(),
            'environment': getattr(settings, 'SENTRY_ENVIRONMENT', ''),
            'frontend_url': getattr(settings, 'FRONTEND_URL', ''),
        },
    )


@require_GET
def health(request):
    """
    GET /api/health/
    Liveness + état des dépendances (DB, Redis, Celery, FedaPay).
    """
    checks = _collect_checks()
    body = _health_body(checks)
    status_code = 200 if checks['db']['ok'] else 503
    return JsonResponse(body, status=status_code)


@require_GET
def health_ready(request):
    """
    GET /api/health/ready/
    Readiness probe — 503 si DB / Redis (si requis) / broker Celery indisponibles.
    """
    checks = _collect_checks()
    ready = _is_ready(checks)
    body = {
        'status': 'ready' if ready else 'not_ready',
        'checks': {
            'db': checks['db'],
            'redis': checks['redis'],
            'celery_broker': checks['celery']['broker'],
        },
    }
    return JsonResponse(body, status=200 if ready else 503)


@require_GET
def celery_health(request):
    """
    GET /api/health/celery/
    Compat — détail Celery uniquement.
    """
    celery = _check_celery()
    broker_ok = celery['broker']['ok']
    body = {
        'status': 'ok' if broker_ok else 'degraded',
        'broker': celery['broker'],
        'workers': celery['workers'],
        'always_eager': celery['always_eager'],
        'beat_schedule': celery['beat_schedule'],
    }
    return JsonResponse(body, status=200 if broker_ok else 503)
