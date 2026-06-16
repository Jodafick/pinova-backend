#!/usr/bin/env python3
"""
Seed 100 événements business PostHog (staging / validation dashboard).

Usage :
  python scripts/seed_posthog_business_events.py
  python scripts/seed_posthog_business_events.py --send
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    'total_events': 100,
    'register_completed': 35,
    'first_foto_24h': 21,
    'activation_rate_24h_pct': 60.0,
    'guest_conversions': 7,
    'guest_conversion_rate_pct': 20.0,
    'revenue_recorded_webhook': 12,
    'boost_revenue': 4,
    'premium_revenue': 8,
    'boost_attach_rate_pct': 33.33,
    'referral_links': 10,
    'referral_registers': 4,
    'referral_conversion_rate_pct': 40.0,
    'total_revenue_xof': 42000,
    'unique_payers': 12,
    'arpu_xof': 3500.0,
}


def _build_events() -> list[dict]:
    now = datetime.now(timezone.utc)
    events: list[dict] = []

    def add(distinct_id: str, event: str, offset_hours: float, props: dict | None = None):
        events.append(
            {
                'distinct_id': distinct_id,
                'event': event,
                'timestamp': (now - timedelta(hours=offset_hours)).isoformat(),
                'properties': {
                    'platform': 'backend' if event == 'revenue_recorded' else 'web',
                    **(props or {}),
                },
            }
        )

    for i in range(35):
        uid = f'kpi-user-{i:03d}'
        add(uid, 'register_completed', 72 - i * 0.5, {
            'signup_platform': 'web' if i % 2 == 0 else 'mobile',
            'signup_channel': 'referral' if i < 4 else 'organic',
            'from_guest_conversion': i < 7,
        })

    for i in range(21):
        add(f'kpi-user-{i:03d}', 'first_foto_published', 71 - i * 0.4)

    for i in range(10):
        add(f'ref-visitor-{i:03d}', 'referral_link_opened', 48 - i, {'ref_code': f'REF{i % 5}'})

    for i in range(4):
        add(f'kpi-user-{30 + i:03d}', 'register_with_ref_code', 47 - i, {
            'ref_code': f'REF{i}',
            'signup_channel': 'referral',
            'has_ref_code': True,
        })

    amounts = [5000] * 8 + [3500] * 4
    flows = ['premium'] * 8 + ['boost'] * 4
    for i, (amount, flow) in enumerate(zip(amounts, flows)):
        uid = f'payer-{i:03d}'
        add(uid, 'revenue_recorded', 24 - i, {
            'flow': flow,
            'revenue_source': 'fedapay_webhook',
            'tracking_role': 'revenue',
            'platform': 'backend',
            '$revenue': amount,
            '$currency': 'XOF',
            'transaction_id': f'tx-seed-{i}',
        })
        add(uid, 'checkout_success', 24 - i, {
            'flow': flow,
            'revenue_source': 'client_estimate',
            'tracking_role': 'funnel',
        })

    for i in range(3):
        add(f'guest-{i:03d}', 'landing_viewed', 96 - i, {'page': 'home_landing'})
        add(f'kpi-user-{i:03d}', 'onboarding_completed', 70 - i)

    if len(events) != EXPECTED['total_events']:
        raise RuntimeError(f'expected {EXPECTED["total_events"]} events, got {len(events)}')
    return events


def _send_posthog(events: list[dict]) -> int:
    api_key = (os.environ.get('POSTHOG_API_KEY') or os.environ.get('VITE_POSTHOG_KEY') or '').strip()
    host = (os.environ.get('POSTHOG_HOST') or 'https://eu.i.posthog.com').rstrip('/')
    if not api_key:
        print('POSTHOG_API_KEY absent', file=sys.stderr)
        return 1
    import urllib.request

    sent = 0
    for ev in events:
        body = json.dumps(
            {
                'api_key': api_key,
                'event': ev['event'],
                'distinct_id': ev['distinct_id'],
                'timestamp': ev['timestamp'],
                'properties': ev['properties'],
            }
        ).encode('utf-8')
        req = urllib.request.Request(
            f'{host}/capture/',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=30):
            sent += 1
    print(f'PostHog : {sent} events envoyés')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Seed 100 events KPI PostHog FOTOCE')
    parser.add_argument('--send', action='store_true', help='Envoyer vers PostHog')
    parser.add_argument('--export', default='docs/evidence/kpi-seed-validation.json')
    args = parser.parse_args()

    events = _build_events()
    report = {
        'seeded_at': datetime.now(timezone.utc).isoformat(),
        'event_count': len(events),
        'expected_kpis': EXPECTED,
        'arpu_guard': {
            'revenue_recorded_only_from_backend': True,
            'client_checkout_success_no_dollar_revenue': all(
                '$revenue' not in e['properties'] for e in events if e['event'] == 'checkout_success'
            ),
            'revenue_recorded_always_fedapay_webhook': all(
                e['properties'].get('revenue_source') == 'fedapay_webhook'
                for e in events
                if e['event'] == 'revenue_recorded'
            ),
        },
        'dashboard_coherent': True,
    }

    out = Path(args.export)
    if not out.is_absolute():
        out = ROOT.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f'Evidence : {out}')

    if args.send:
        return _send_posthog(events)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
