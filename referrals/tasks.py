"""Tâches Celery — referrals (récompenses + bonus rétention)."""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from pinova_backend.celery import PinovaTask


def _run_management(command: str, **options) -> dict:
    call_command(command, **options)
    return {'command': command, 'finished_at': timezone.now().isoformat(), **options}


@shared_task(bind=True, base=PinovaTask, name='referrals.referral_reward_scan')
def referral_reward_scan(self, limit: int = 3000) -> dict:
    """Finalise les récompenses referral en attente (anti-fraude)."""
    limit = max(1, min(int(limit), 50_000))
    return _run_management('referral_reward_scan', limit=limit)


@shared_task(bind=True, base=PinovaTask, name='referrals.referral_retention_scan')
def referral_retention_scan(self, limit: int = 2000) -> dict:
    """Attribue les bonus rétention (filleuls actifs après 7 j)."""
    limit = max(1, min(int(limit), 20_000))
    return _run_management('referral_retention_scan', limit=limit)
