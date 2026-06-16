"""Tâches Celery — fotos (digest, stories éphémères, publication planifiée)."""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from fotoce_backend.celery import FotoceTask


def _run_management(command: str, **options) -> dict:
    call_command(command, **options)
    return {'command': command, 'finished_at': timezone.now().isoformat(), **options}


@shared_task(bind=True, base=FotoceTask, name='fotos.send_weekly_pro_digest')
def send_weekly_pro_digest(self) -> dict:
    """Digest hebdomadaire Pro (vues 7 j + push + e-mail)."""
    return _run_management('send_weekly_pro_digest')


@shared_task(bind=True, base=FotoceTask, name='fotos.purge_expired_ephemeral_stories')
def purge_expired_ephemeral_stories(self) -> dict:
    """Hard-delete stories Plus/Pro éphémères après story_expires_at."""
    return _run_management('purge_expired_ephemeral_stories')


@shared_task(bind=True, base=FotoceTask, name='fotos.publish_scheduled_fotos')
def publish_scheduled_fotos(self, limit: int = 1000) -> dict:
    """Publie les fotos dont scheduled_publish_at est dépassé."""
    limit = max(1, int(limit))
    return _run_management('publish_scheduled_fotos', limit=limit)


# Enregistrement tâches Typesense (autodiscover Celery)
from fotos.search import tasks as _search_tasks  # noqa: E402,F401
