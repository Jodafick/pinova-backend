#!/usr/bin/env python3
"""
Load test recherche header-search — objectif : 50 req/s, p95 < 300 ms.

Usage :
  python scripts/load_test_search.py --url http://127.0.0.1:8000/api/pins/header-search/ --q tattoo --rps 50 --duration 10

Prérequis : serveur Django/API accessible (gunicorn ou runserver).
"""

from __future__ import annotations

import argparse
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def _fetch(url: str, timeout: float) -> tuple[float, int | None, str | None]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read()
            return (time.perf_counter() - started) * 1000.0, resp.status, None
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - started) * 1000.0, exc.code, str(exc)
    except Exception as exc:
        return (time.perf_counter() - started) * 1000.0, None, str(exc)


def run_load_test(base_url: str, query: str, rps: int, duration: int, timeout: float) -> int:
    params = urllib.parse.urlencode({'q': query, 'limit': '8'})
    url = f"{base_url.rstrip('/')}/?{params}" if '?' not in base_url else f"{base_url}&{params}"

    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()
    stop_at = time.perf_counter() + duration
    interval = 1.0 / max(rps, 1)

    def worker():
        while time.perf_counter() < stop_at:
            tick = time.perf_counter()
            ms, status, err = _fetch(url, timeout)
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

    if not latencies:
        print('Aucune requête complétée.')
        return 1

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    actual_rps = len(latencies) / duration

    print(f'URL          : {url}')
    print(f'Duration     : {duration}s  target RPS={rps}  actual RPS={actual_rps:.1f}')
    print(f'Requests     : {len(latencies)}  errors={len(errors)}')
    print(f'Latency ms   : min={min(latencies):.0f}  avg={statistics.mean(latencies):.0f}  p50={p50:.0f}  p95={p95:.0f}  p99={p99:.0f}')

    ok_rps = actual_rps >= rps * 0.9
    ok_p95 = p95 < 300
    if ok_rps and ok_p95:
        print('PASS — p95 < 300 ms et débit cible atteint.')
        return 0
    if not ok_p95:
        print('FAIL — p95 >= 300 ms')
    if not ok_rps:
        print('FAIL — débit insuffisant')
    return 1


def main():
    parser = argparse.ArgumentParser(description='Load test header-search Pinova')
    parser.add_argument('--url', default='http://127.0.0.1:8000/api/pins/header-search/')
    parser.add_argument('--q', default='tattoo')
    parser.add_argument('--rps', type=int, default=50)
    parser.add_argument('--duration', type=int, default=10)
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args()
    raise SystemExit(run_load_test(args.url, args.q, args.rps, args.duration, args.timeout))


if __name__ == '__main__':
    main()
