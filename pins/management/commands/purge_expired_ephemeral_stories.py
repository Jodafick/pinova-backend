"""Supprime les stories Plus/Pro éphémères après story_expires_at (fichiers inclus).

Production : Celery Beat `pins-purge-ephemeral-stories` (chaque heure :15 UTC).
Secours : python manage.py purge_expired_ephemeral_stories
"""

from __future__ import annotations

from django.utils import timezone
from django.core.management.base import BaseCommand

from pins.models import Pin


class Command(BaseCommand):
    help = (
        'Hard-delete pins with story_ephemeral=True past story_expires_at. '
        'Classic pins in story format (story_ephemeral=False) are never removed.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = Pin.objects.filter(
            story_ephemeral=True,
            is_story=True,
            story_expires_at__isnull=False,
            story_expires_at__lte=now,
        )
        total = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f'purge_expired_ephemeral_stories: deleted={total}'))
