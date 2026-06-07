#!/usr/bin/env python3
"""
Crée ou met à jour le dashboard business PINOVA dans PostHog (API EU).

Usage:
  export POSTHOG_PERSONAL_API_KEY=phx_...
  export POSTHOG_PROJECT_ID=12345
  export POSTHOG_HOST=https://eu.posthog.com   # optionnel
  python scripts/setup_posthog_business_dashboard.py

Référence manuelle : docs/posthog/business-dashboard.json
Interprétation KPIs : docs/BUSINESS-METRICS.md
Evidence : docs/evidence/posthog-analytics-live.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CONFIG_PATH = ROOT / 'docs' / 'posthog' / 'business-dashboard.json'
EVIDENCE_PATH = ROOT / 'docs' / 'evidence' / 'posthog-analytics-live.json'

sys.path.insert(0, str(SCRIPT_DIR))
from verify_posthog_business_events import verify_events  # noqa: E402

DASHBOARD_NAME = 'PINOVA — Business'


def _api_base() -> str:
    host = (os.environ.get('POSTHOG_HOST') or 'https://eu.posthog.com').rstrip('/')
    if host.endswith('.i.posthog.com'):
        host = host.replace('.i.posthog.com', '.posthog.com')
    return host


def _headers(api_key: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = request.Request(url, data=data, headers=_headers(api_key), method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'PostHog API {exc.code}: {detail}') from exc


def _project_url(project_id: str, path: str) -> str:
    return f'{_api_base()}/api/projects/{project_id}/{path.lstrip("/")}'


def _find_dashboard(project_id: str, api_key: str) -> dict | None:
    data = _request('GET', _project_url(project_id, 'dashboards/'), api_key)
    for dash in data.get('results', []):
        if dash.get('name') == DASHBOARD_NAME:
            return dash
    return None


def _list_insight_names(project_id: str, api_key: str) -> set[str]:
    names: set[str] = set()
    url = _project_url(project_id, 'insights/?limit=200')
    while url:
        data = _request('GET', url, api_key)
        for row in data.get('results', []):
            name = (row.get('name') or '').strip()
            if name:
                names.add(name)
        url = data.get('next') or ''
    return names


def _get_dashboard(project_id: str, api_key: str, dashboard_id: int) -> dict:
    return _request('GET', _project_url(project_id, f'dashboards/{dashboard_id}/'), api_key)


def _create_insight(project_id: str, api_key: str, spec: dict) -> dict:
    filters = spec.get('filters', {})
    payload = {
        'name': spec['name'],
        'filters': filters,
        'query': {
            'kind': spec.get('kind', 'TrendsQuery'),
            'filter': filters,
        },
        'tags': ['pinova', 'business'],
    }
    return _request('POST', _project_url(project_id, 'insights/'), api_key, payload)


def _save_dashboard_tiles(project_id: str, api_key: str, dashboard_id: int, tiles: list) -> None:
    _request(
        'PATCH',
        _project_url(project_id, f'dashboards/{dashboard_id}/'),
        api_key,
        {'tiles': tiles},
    )


def _attach_tile(
    project_id: str,
    api_key: str,
    dashboard_id: int,
    insight_id: int,
    row: int,
    col: int,
    tiles: list,
) -> None:
    tiles.append(
        {
            'insight': insight_id,
            'layouts': {
                'sm': {'x': col, 'y': row, 'w': 6, 'h': 5},
                'lg': {'x': col, 'y': row, 'w': 6, 'h': 5},
            },
        }
    )


def _write_evidence(payload: dict) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Evidence : {EVIDENCE_PATH}')


def main() -> int:
    api_key = (os.environ.get('POSTHOG_PERSONAL_API_KEY') or '').strip()
    project_id = (os.environ.get('POSTHOG_PROJECT_ID') or '').strip()
    if not api_key or not project_id:
        print('POSTHOG_PERSONAL_API_KEY et POSTHOG_PROJECT_ID sont requis.', file=sys.stderr)
        return 1
    if not CONFIG_PATH.is_file():
        print(f'Config introuvable: {CONFIG_PATH}', file=sys.stderr)
        return 1

    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    existing = _find_dashboard(project_id, api_key)
    if existing:
        dashboard = existing
        print(f'Dashboard existant: {dashboard["id"]} — ajout des insights manquants')
    else:
        dashboard = _request(
            'POST',
            _project_url(project_id, 'dashboards/'),
            api_key,
            {'name': DASHBOARD_NAME, 'description': config.get('description', '')},
        )
        print(f'Dashboard créé: {dashboard.get("id")}')

    dashboard_id = dashboard['id']
    dashboard_url = f'{_api_base()}/project/{project_id}/dashboard/{dashboard_id}'
    existing_names = _list_insight_names(project_id, api_key)
    dash_detail = _get_dashboard(project_id, api_key, dashboard_id)
    tiles = list(dash_detail.get('tiles') or [])
    created_insights: list[dict] = []

    insights = config.get('insights', [])
    for idx, spec in enumerate(insights):
        name = spec['name']
        if name in existing_names:
            print(f'  = {name} (déjà présent)')
            continue
        created = _create_insight(project_id, api_key, spec)
        insight_id = created.get('id')
        if not insight_id:
            print(f'  Échec insight: {name}', file=sys.stderr)
            continue
        row = (idx // 2) * 5
        col = (idx % 2) * 6
        _attach_tile(project_id, api_key, dashboard_id, insight_id, row, col, tiles)
        created_insights.append({'name': name, 'id': insight_id, 'key': spec.get('key')})
        print(f'  + {name} (insight {insight_id})')

    if created_insights:
        _save_dashboard_tiles(project_id, api_key, dashboard_id, tiles)

    print('\n=== Vérification événements ===')
    events_report = verify_events(project_id=project_id, api_key=api_key)
    print(f"Events : {events_report['present_count']}/{events_report['required_count']}")
    if events_report['missing_events']:
        print('MANQUANTS :', ', '.join(events_report['missing_events']))

    evidence = {
        'deployed_at': datetime.now(timezone.utc).isoformat(),
        'environment': os.environ.get('POSTHOG_ENV', 'production'),
        'posthog_host': _api_base(),
        'project_id': project_id,
        'dashboard': {
            'id': dashboard_id,
            'name': DASHBOARD_NAME,
            'url': dashboard_url,
        },
        'insights_created': created_insights,
        'insights_config': [
            {'key': s.get('key'), 'name': s.get('name'), 'kind': s.get('kind')}
            for s in insights
        ],
        'events_validation': events_report,
    }
    _write_evidence(evidence)

    print(f'\nDashboard: {dashboard_url}')
    print('Documentation: docs/ANALYTICS-LIVE-VALIDATION.md')
    return 0 if events_report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
