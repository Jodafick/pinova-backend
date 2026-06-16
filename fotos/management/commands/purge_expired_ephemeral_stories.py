"""Supprime les stories Plus/Pro éphémères après story_expires_at (fichiers inclus).

Production : Celery Beat `fotos-purge-ephemeral-stories` (chaque heure :15 UTC).
Secours : python manage.py purge_expired_ephemeral_stories
"""

from __future__ import annotations

from django.utils import timezone
from django.core.management.base import BaseCommand

from fotos.models import Foto


class Command(BaseCommand):
    help = (
        'Hard-delete fotos with story_ephemeral=True past story_expires_at. '
        'Classic fotos in story format (story_ephemeral=False) are never removed.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = Foto.objects.filter(
            story_ephemeral=True,
            is_story=True,
            story_expires_at__isnull=False,
            story_expires_at__lte=now,
        )
        total = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f'purge_expired_ephemeral_stories: deleted={total}'))
