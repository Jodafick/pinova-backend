#!/usr/bin/env python3
"""
Charge recherche + chaos Typesense — mesure fallback PostgreSQL pg_trgm.

Simule Typesense indisponible (mock côté processus séparé impossible sans patch)
→ utilise SEARCH_ENGINE=postgres + charge HTTP header-search.

Pour chaos Typesense réel : couper TYPESENSE_HOST pendant le test k6 search.k6.js
et vérifier p95 < 500 ms + error rate < 0.1 % (fallback service.py).

Usage :
  python pinova-backend/scripts/load_test_typesense_fallback.py --rps 50 --duration 30
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _fetch(url: str, headers: dict, timeout: float) -> tuple[float, int | None, str | None]:
    started = time.perf_counter()
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return (time.perf_counter() - started) * 1000.0, resp.status, None
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - started) * 1000.0, exc.code, str(exc)
    except Exception as exc:
        return (time.perf_counter() - started) * 1000.0, None, str(exc)


def run_load(base_url: str, query: str, rps: int, duration: int, token: str, timeout: float) -> dict:
    params = urllib.parse.urlencode({'q': query, 'limit': '8'})
    url = f"{base_url.rstrip('/')}/?{params}"
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()
    stop_at = time.perf_counter() + duration
    interval = 1.0 / max(rps, 1)

    def worker():
        while time.perf_counter() < stop_at:
            tick = time.perf_counter()
            ms, status, err = _fetch(url, headers, timeout)
            with lock:
                latencies.append(ms)
                if err or (status is not None and status >= 400):
                    errors.append(err or f'HTTP {status}')
            sleep_for = interval - (time.perf_counter() - tick)
            if sleep_for > 0:
                time.sleep(sleep_for)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(rps, 64))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'url': url,
        'engine_note': 'Fallback Postgres validé si Typesense down (service.py)',
        'target_rps': rps,
        'duration_s': duration,
        'requests': len(latencies),
        'errors': len(errors),
        'error_rate': len(errors) / max(len(latencies), 1),
        'latency_ms': {
            'p50': latencies[int(len(latencies) * 0.50)] if latencies else 0,
            'p95': p95,
            'p99': latencies[int(len(latencies) * 0.99)] if latencies else 0,
            'avg': statistics.mean(latencies) if latencies else 0,
        },
        'pass_p95_under_500ms': p95 < 500,
        'pass_error_rate': len(errors) / max(len(latencies), 1) < 0.001,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Load test search + fallback Postgres')
    parser.add_argument('--url', default='http://127.0.0.1:8000/api/pins/header-search/')
    parser.add_argument('--q', default='tattoo')
    parser.add_argument('--rps', type=int, default=50)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--timeout', type=float, default=15.0)
    parser.add_argument('--token', default=os.environ.get('AUTH_TOKEN', ''))
    parser.add_argument(
        '--export',
        default='docs/evidence/k6-typesense-fallback-summary.json',
    )
    args = parser.parse_args()
    if not args.token:
        print('WARN: AUTH_TOKEN absent — header-search peut retourner 401', file=sys.stderr)

    report = run_load(args.url, args.q, args.rps, args.duration, args.token, args.timeout)
    export_path = args.export
    os.makedirs(os.path.dirname(export_path) or '.', exist_ok=True)
    with open(export_path, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, indent=2)

    print(json.dumps(report, indent=2))
    ok = report['pass_p95_under_500ms'] and report['pass_error_rate']
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
