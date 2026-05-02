"""Publication planifiée : une requête UPDATE indexée par échéance (léger).

À planifier via cron (ex. toutes les 5 minutes) :
    python manage.py publish_scheduled_pins
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pins.models import Pin


class Command(BaseCommand):
    help = 'Publie les pins dont scheduled_publish_at est dépassé (batch UPDATE).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Nombre maximum de pins traités par exécution (défaut 1000).',
        )

    def handle(self, *args, **options):
        limit = max(1, int(options['limit']))
        now = timezone.now()
        qs = Pin.objects.filter(scheduled_publish_at__isnull=False, scheduled_publish_at__lte=now)
        ids = list(qs.values_list('pk', flat=True)[:limit])
        updated = Pin.objects.filter(pk__in=ids).update(scheduled_publish_at=None)
        self.stdout.write(self.style.SUCCESS(f'Pins publiés : {updated} (limite {limit}).'))
