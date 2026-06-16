"""Tâches Celery — accounts (abonnements, suppressions planifiées)."""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from fotoce_backend.celery import FotoceTask


def _run_management(command: str, **options) -> dict:
    call_command(command, **options)
    return {'command': command, 'finished_at': timezone.now().isoformat(), **options}


@shared_task(bind=True, base=FotoceTask, name='accounts.enforce_subscriptions_due')
def enforce_subscriptions_due(self) -> dict:
    """Applique le plan programmé ou Free pour les abonnements échus."""
    return _run_management('enforce_subscriptions_due')


@shared_task(bind=True, base=FotoceTask, name='accounts.purge_scheduled_account_deletions')
def purge_scheduled_account_deletions(self) -> dict:
    """Supprime les comptes dont account_scheduled_deletion_at est dépassé."""
    return _run_management('purge_scheduled_account_deletions')


@shared_task(bind=True, base=FotoceTask, name='accounts.discovery_streak_reminder')
def discovery_streak_reminder(self, limit: int = 5000) -> dict:
    """Push J+1 si streak discovery à risque."""
    limit = max(1, min(int(limit), 20_000))
    return _run_management('send_discovery_streak_reminders', limit=limit)


@shared_task(bind=True, base=FotoceTask, name='accounts.reactivation_j7_email')
def reactivation_j7_email(self, limit: int = 2000) -> dict:
    """Email J+7 inactif — nouveaux fotos des créateurs suivis."""
    limit = max(1, min(int(limit), 10_000))
    return _run_management('send_reactivation_j7_emails', limit=limit)


@shared_task(bind=True, base=FotoceTask, name='accounts.reactivation_j30_email')
def reactivation_j30_email(self, limit: int = 2000) -> dict:
    """Email J+30 inactif — résumé mois + CTA concours/referral."""
    limit = max(1, min(int(limit), 10_000))
    return _run_management('send_reactivation_j30_emails', limit=limit)


@shared_task(bind=True, base=FotoceTask, name='accounts.export_user_data')
def export_user_data(self, job_id: int) -> dict:
    """Génère l'archive ZIP RGPD et envoie l'e-mail de téléchargement."""
    from django.contrib.auth.models import User

    from accounts.gdpr_export import save_export_zip
    from accounts.gdpr_views import _send_export_ready_email
    from accounts.models import DataExportJob

    try:
        job = DataExportJob.objects.select_related('user').get(pk=job_id)
    except DataExportJob.DoesNotExist:
        return {'ok': False, 'error': 'job_not_found', 'job_id': job_id}

    job.status = DataExportJob.STATUS_PROCESSING
    job.save(update_fields=['status'])
    user = job.user
    try:
        rel_path = save_export_zip(user, job.id)
        job.file_path = rel_path
        job.status = DataExportJob.STATUS_READY
        job.completed_at = timezone.now()
        job.save(update_fields=['file_path', 'status', 'completed_at'])
        _send_export_ready_email(user, job)
        return {'ok': True, 'job_id': job_id, 'user_id': user.id}
    except Exception as exc:
        job.status = DataExportJob.STATUS_FAILED
        job.error_message = str(exc)[:500]
        job.save(update_fields=['status', 'error_message'])
        return {'ok': False, 'job_id': job_id, 'error': job.error_message}
