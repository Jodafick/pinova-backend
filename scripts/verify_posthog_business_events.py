#!/usr/bin/env python3
"""
Vérifie la présence des événements business PINOVA dans PostHog (prod/staging).

Usage:
  export POSTHOG_PERSONAL_API_KEY=phx_...
  export POSTHOG_PROJECT_ID=12345
  python scripts/verify_posthog_business_events.py
  python scripts/verify_posthog_business_events.py --json docs/evidence/posthog-events-validation.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[2]

# Événements requis — exact ou préfixe (suffixe *)
REQUIRED_EVENTS: list[str] = [
    'landing_viewed',
    'register_started',
    'register_completed',
    'register_with_ref_code',
    'onboarding_started',
    'onboarding_step_viewed',
    'onboarding_step_completed',
    'onboarding_step_skipped',
    'onboarding_completed',
    'first_pin_published',
    'premium_viewed',
    'checkout_started',
    'checkout_returned',
    'checkout_success',
    'revenue_recorded',
    'referral_link_opened',
    'retention_cohort_j1',
    'retention_cohort_j7',
    'retention_cohort_j30',
]


def _api_base() -> str:
    host = (os.environ.get('POSTHOG_HOST') or 'https://eu.posthog.com').rstrip('/')
    if host.endswith('.i.posthog.com'):
        host = host.replace('.i.posthog.com', '.posthog.com')
    return host


def _headers(api_key: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}


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


def _fetch_event_definitions(project_id: str, api_key: str) -> set[str]:
    names: set[str] = set()
    url = _project_url(project_id, 'event_definitions/?limit=500')
    while url:
        data = _request('GET', url, api_key)
        for row in data.get('results', []):
            name = (row.get('name') or '').strip()
            if name:
                names.add(name)
        next_link = data.get('next')
        url = next_link if next_link else ''
    return names


def _hogql_recent_counts(project_id: str, api_key: str, events: list[str]) -> dict[str, int]:
    """Compte les events sur 90 jours (preuve d'activité live)."""
    in_list = ', '.join(f"'{e}'" for e in events)
    query = f"""
        SELECT event, count() AS c
        FROM events
        WHERE timestamp >= now() - INTERVAL 90 DAY
          AND event IN ({in_list})
        GROUP BY event
    """
    try:
        data = _request(
            'POST',
            _project_url(project_id, 'query/'),
            api_key,
            {'query': {'kind': 'HogQLQuery', 'query': query}},
        )
    except RuntimeError:
        return {}
    counts: dict[str, int] = {}
    for row in data.get('results', []) or []:
        if isinstance(row, list) and len(row) >= 2:
            counts[str(row[0])] = int(row[1])
    return counts


def verify_events(*, project_id: str, api_key: str, hogql: bool = True) -> dict:
    defined = _fetch_event_definitions(project_id, api_key)
    missing = [e for e in REQUIRED_EVENTS if e not in defined]
    present = [e for e in REQUIRED_EVENTS if e in defined]
    counts = _hogql_recent_counts(project_id, api_key, present) if hogql and present else {}
    inactive = [e for e in present if counts.get(e, 0) == 0]
    return {
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'project_id': project_id,
        'posthog_host': _api_base(),
        'required_count': len(REQUIRED_EVENTS),
        'present_count': len(present),
        'missing_events': missing,
        'present_events': present,
        'inactive_90d': inactive,
        'event_counts_90d': counts,
        'ok': len(missing) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Vérifie les événements business PostHog PINOVA')
    parser.add_argument('--json', help='Chemin export JSON evidence')
    parser.add_argument('--no-hogql', action='store_true', help='Skip comptage HogQL 90j')
    args = parser.parse_args()

    api_key = (os.environ.get('POSTHOG_PERSONAL_API_KEY') or '').strip()
    project_id = (os.environ.get('POSTHOG_PROJECT_ID') or '').strip()
    if not api_key or not project_id:
        print('POSTHOG_PERSONAL_API_KEY et POSTHOG_PROJECT_ID sont requis.', file=sys.stderr)
        return 1

    report = verify_events(project_id=project_id, api_key=api_key, hogql=not args.no_hogql)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Evidence : {out}')

    print(f"Présents : {report['present_count']}/{report['required_count']}")
    if report['missing_events']:
        print('MANQUANTS :', ', '.join(report['missing_events']))
    if report.get('inactive_90d'):
        print('Sans activité 90j (définis mais 0 event) :', ', '.join(report['inactive_90d']))

    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
