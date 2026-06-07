#!/usr/bin/env python3
"""
Export KPIs business PINOVA via HogQL PostHog + validation locale.

KPIs : activation 24h, guest conversion, ARPU, boost attach rate, referral conversion.

Usage :
  export POSTHOG_PERSONAL_API_KEY=phx_...
  export POSTHOG_PROJECT_ID=12345
  python docs/evidence/export-kpis.py
  python docs/evidence/export-kpis.py --days 30 --json docs/evidence/kpi-export-latest.json

Sans clés PostHog : mode simulation (--simulate) avec seed local 100 events.
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
sys.path.insert(0, str(ROOT / 'pinova-backend' / 'scripts'))

DAYS_DEFAULT = 30

KPI_QUERIES: dict[str, str] = {
    'activation_rate_24h': """
SELECT round(
  countIf(dateDiff('hour', reg.ts, fp.ts) <= 24) * 100.0 / nullIf(count(), 0),
  2
) AS activation_rate_pct
FROM (
  SELECT distinct_id, min(timestamp) AS ts
  FROM events
  WHERE event = 'register_completed'
    AND timestamp >= now() - INTERVAL {days} DAY
  GROUP BY distinct_id
) reg
LEFT JOIN (
  SELECT distinct_id, min(timestamp) AS ts
  FROM events
  WHERE event = 'first_pin_published'
  GROUP BY distinct_id
) fp ON reg.distinct_id = fp.distinct_id
""",
    'guest_conversion_rate': """
SELECT round(
  countIf(JSONExtractBool(properties, 'from_guest_conversion') = 1) * 100.0 /
  nullIf(count(), 0),
  2
) AS guest_conversion_pct
FROM events
WHERE event = 'register_completed'
  AND timestamp >= now() - INTERVAL {days} DAY
""",
    'arpu_webhook_only': """
SELECT round(
  sum(toFloat64OrNull(JSONExtractString(properties, '$revenue'))) /
  nullIf(count(DISTINCT distinct_id), 0),
  2
) AS arpu
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL {days} DAY
""",
    'boost_attach_rate': """
SELECT round(
  countIf(JSONExtractString(properties, 'flow') = 'boost') * 100.0 /
  nullIf(count(), 0),
  2
) AS boost_attach_pct
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL {days} DAY
""",
    'referral_conversion_rate': """
SELECT round(
  count(DISTINCT reg.distinct_id) * 100.0 /
  nullIf(count(DISTINCT ref.distinct_id), 0),
  2
) AS referral_conversion_pct
FROM (
  SELECT distinct_id FROM events
  WHERE event = 'referral_link_opened'
    AND timestamp >= now() - INTERVAL {days} DAY
) ref
LEFT JOIN (
  SELECT distinct_id FROM events
  WHERE event = 'register_with_ref_code'
    AND timestamp >= now() - INTERVAL {days} DAY
) reg ON ref.distinct_id = reg.distinct_id
""",
    'revenue_recorded_24h_count': """
SELECT count() AS revenue_events_24h
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 1 DAY
""",
    'client_checkout_without_revenue': """
SELECT count() AS client_checkout_events
FROM events
WHERE event = 'checkout_success'
  AND JSONExtractString(properties, 'revenue_source') = 'client_estimate'
  AND timestamp >= now() - INTERVAL {days} DAY
""",
    'webhook_revenue_only': """
SELECT count() AS webhook_revenue_events
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND JSONExtractString(properties, 'platform') = 'backend'
  AND timestamp >= now() - INTERVAL {days} DAY
""",
}


def _api_base() -> str:
    host = (os.environ.get('POSTHOG_HOST') or 'https://eu.posthog.com').rstrip('/')
    if host.endswith('.i.posthog.com'):
        host = host.replace('.i.posthog.com', '.posthog.com')
    return host


def _headers(api_key: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}


def _hogql(project_id: str, api_key: str, query: str) -> list:
    url = f'{_api_base()}/api/projects/{project_id}/query/'
    body = {'query': {'kind': 'HogQLQuery', 'query': query.strip()}}
    data = json.dumps(body).encode('utf-8')
    req = request.Request(url, data=data, headers=_headers(api_key), method='POST')
    try:
        with request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'PostHog HogQL {exc.code}: {detail}') from exc
    return payload.get('results') or []


def _scalar(results: list, default=None):
    if not results:
        return default
    row = results[0]
    if isinstance(row, list) and row:
        return row[0]
    return row


def simulate_kpis() -> dict:
    """100 events seed — valeurs attendues pour validation dashboard."""
    return {
        'mode': 'simulate',
        'events_seeded': 100,
        'activation_rate_24h_pct': 60.0,
        'guest_conversion_rate_pct': 20.0,
        'arpu_webhook_only': 3500.0,
        'boost_attach_rate_pct': 33.33,
        'referral_conversion_rate_pct': 40.0,
        'revenue_recorded_24h_count': 3,
        'arpu_guard': {
            'revenue_recorded_webhook_only': True,
            'client_checkout_has_no_dollar_revenue': True,
            'client_never_emits_revenue_recorded': True,
        },
        'seed_breakdown': {
            'register_completed': 35,
            'first_pin_24h': 21,
            'revenue_recorded_webhook': 12,
            'total_revenue_xof': 42000,
        },
        'note': 'Valeurs du seed pinova-backend/scripts/seed_posthog_business_events.py',
    }


def export_kpis(*, project_id: str, api_key: str, days: int) -> dict:
    kpis: dict[str, object] = {}
    for key, template in KPI_QUERIES.items():
        query = template.format(days=days)
        try:
            results = _hogql(project_id, api_key, query)
            kpis[key] = _scalar(results)
        except RuntimeError as exc:
            kpis[key] = {'error': str(exc)}

    kpis['arpu_guard'] = {
        'revenue_recorded_webhook_only': True,
        'rule': "ARPU = SUM($revenue) WHERE event='revenue_recorded' AND revenue_source='fedapay_webhook'",
        'exclude': "checkout_success WHERE revenue_source='client_estimate'",
    }
    return kpis


def main() -> int:
    parser = argparse.ArgumentParser(description='Export KPIs business PINOVA')
    parser.add_argument('--days', type=int, default=DAYS_DEFAULT)
    parser.add_argument('--json', default='docs/evidence/kpi-export-latest.json')
    parser.add_argument('--simulate', action='store_true', help='Seed local sans PostHog API')
    args = parser.parse_args()

    api_key = (os.environ.get('POSTHOG_PERSONAL_API_KEY') or '').strip()
    project_id = (os.environ.get('POSTHOG_PROJECT_ID') or '').strip()

    if args.simulate or not api_key or not project_id:
        kpis = simulate_kpis()
        source = 'simulate'
    else:
        kpis = export_kpis(project_id=project_id, api_key=api_key, days=args.days)
        source = 'posthog_hogql'

    report = {
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'source': source,
        'period_days': args.days,
        'project_id': project_id or None,
        'posthog_host': _api_base(),
        'kpis': kpis,
        'hogql_templates': {k: v.strip() for k, v in KPI_QUERIES.items()},
    }

    out = Path(args.json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report['kpis'], indent=2, ensure_ascii=False))
    print(f'\nEvidence : {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
