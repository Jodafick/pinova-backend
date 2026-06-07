"""
Application Celery Pinova — broker Redis, beat planifié, retry exponentiel.

Lancer en dev :
  celery -A pinova_backend worker -l info
  celery -A pinova_backend beat -l info

Voir docs/DEPLOY.md pour Render / Railway.
"""
from __future__ import annotations

import logging
import os

from celery import Celery, Task
from celery.schedules import crontab

logger = logging.getLogger('pinova.celery')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')


class PinovaTask(Task):
    """Retry 3× backoff exponentiel + log dead-letter sur échec final."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            'celery dead letter task=%s id=%s args=%s kwargs=%s error=%s',
            self.name,
            task_id,
            args,
            kwargs,
            exc,
            exc_info=einfo,
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


app = Celery('pinova')
app.Task = PinovaTask
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ── Beat schedule (UTC) — remplace les crons manage.py en production ──────────
# | Clé beat                         | Tâche                              | Ancien cron        |
# |----------------------------------|------------------------------------|--------------------|
# | pins-send-weekly-pro-digest      | pins.send_weekly_pro_digest        | lun 09:00          |
# | pins-purge-ephemeral-stories     | pins.purge_expired_ephemeral_stories | */h :15          |
# | pins-publish-scheduled           | pins.publish_scheduled_pins        | */5 min            |
# | accounts-enforce-subscriptions   | accounts.enforce_subscriptions_due | */10 min           |
# | accounts-purge-deletions         | accounts.purge_scheduled_account_deletions | 03:00 daily |
# | referrals-reward-scan            | referrals.referral_reward_scan     | */15 min           |
# | referrals-retention-scan         | referrals.referral_retention_scan  | 04:00 daily        |

app.conf.beat_schedule = {
    'pins-send-weekly-pro-digest': {
        'task': 'pins.send_weekly_pro_digest',
        'schedule': crontab(hour=9, minute=0, day_of_week=1),
        'options': {'expires': 3600},
    },
    'pins-purge-ephemeral-stories': {
        'task': 'pins.purge_expired_ephemeral_stories',
        'schedule': crontab(minute=15),
        'options': {'expires': 3000},
    },
    'pins-publish-scheduled': {
        'task': 'pins.publish_scheduled_pins',
        'schedule': crontab(minute='*/5'),
        'kwargs': {'limit': 1000},
        'options': {'expires': 240},
    },
    'accounts-enforce-subscriptions': {
        'task': 'accounts.enforce_subscriptions_due',
        'schedule': crontab(minute='*/10'),
        'options': {'expires': 480},
    },
    'accounts-purge-deletions': {
        'task': 'accounts.purge_scheduled_account_deletions',
        'schedule': crontab(hour=3, minute=0),
        'options': {'expires': 3600},
    },
    'referrals-reward-scan': {
        'task': 'referrals.referral_reward_scan',
        'schedule': crontab(minute='*/15'),
        'kwargs': {'limit': 3000},
        'options': {'expires': 720},
    },
    'referrals-retention-scan': {
        'task': 'referrals.referral_retention_scan',
        'schedule': crontab(hour=4, minute=0),
        'kwargs': {'limit': 2000},
        'options': {'expires': 3600},
    },
    'accounts-discovery-streak-reminder': {
        'task': 'accounts.discovery_streak_reminder',
        'schedule': crontab(hour=18, minute=0),
        'kwargs': {'limit': 5000},
        'options': {'expires': 3600},
    },
    'accounts-reactivation-j7-email': {
        'task': 'accounts.reactivation_j7_email',
        'schedule': crontab(hour=10, minute=0),
        'kwargs': {'limit': 2000},
        'options': {'expires': 3600},
    },
    'accounts-reactivation-j30-email': {
        'task': 'accounts.reactivation_j30_email',
        'schedule': crontab(hour=10, minute=30),
        'kwargs': {'limit': 2000},
        'options': {'expires': 3600},
    },
    'pins-reindex-typesense-nightly': {
        'task': 'pins.reindex_typesense',
        'schedule': crontab(hour=2, minute=30),
        'kwargs': {'batch_size': 500},
        'options': {'expires': 7200},
    },
}
