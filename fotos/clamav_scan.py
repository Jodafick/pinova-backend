"""Scan antivirus ClamAV optionnel (async, non bloquant)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading

from django.conf import settings

logger = logging.getLogger('fotoce.upload.clamav')


def enqueue_clamav_scan(payload: bytes, *, media_kind: str, user_id: int | None) -> None:
    worker = threading.Thread(
        target=_scan_worker,
        args=(payload, media_kind, user_id),
        daemon=True,
        name='fotoce-clamav-scan',
    )
    worker.start()


def _scan_worker(payload: bytes, media_kind: str, user_id: int | None) -> None:
    try:
        verdict = _scan_bytes(payload)
    except Exception as exc:
        logger.warning('clamav_scan_failed kind=%s user=%s err=%s', media_kind, user_id, exc)
        return
    if verdict:
        logger.error(
            'clamav_infected_upload kind=%s user=%s signature=%s',
            media_kind,
            user_id,
            verdict,
        )


def _scan_bytes(payload: bytes) -> str | None:
    host = getattr(settings, 'CLAMD_HOST', '127.0.0.1')
    port = int(getattr(settings, 'CLAMD_PORT', 3310) or 3310)
    try:
        import pyclamd

        client = pyclamd.ClamdNetworkSocket(host=host, port=port)
        if client.ping():
            result = client.scan_stream(payload)
            if result:
                return next(iter(result.values()))
    except ImportError:
        pass
    except Exception as exc:
        logger.debug('pyclamd_unavailable: %s', exc)

    if shutil.which('clamdscan'):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tmp:
            tmp.write(payload)
            path = tmp.name
        try:
            proc = subprocess.run(
                ['clamdscan', '--no-summary', path],
                capture_output=True,
                text=True,
                timeout=int(getattr(settings, 'CLAMD_SCAN_TIMEOUT_SECONDS', 120) or 120),
            )
            if proc.returncode == 1:
                return (proc.stdout or proc.stderr or 'FOUND').strip()[:200]
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    return None
