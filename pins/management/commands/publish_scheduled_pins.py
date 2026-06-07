"""Publication planifiée : notif auteur puis reset scheduled_publish_at.

Production : Celery Beat `pins-publish-scheduled` (*/5 min UTC).
Secours : python manage.py publish_scheduled_pins
"""

from django.core.management.base import BaseCommand

from pins.models import Pin
from pins.scheduled_publish_utils import publish_due_scheduled_pins


class Command(BaseCommand):
    help = 'Publie les pins dont scheduled_publish_at est dépassé ; notif auteur puis batch UPDATE.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Nombre maximum de pins traités par exécution (défaut 1000).',
        )

    def handle(self, *args, **options):
        limit = max(1, int(options['limit']))
        n = publish_due_scheduled_pins(Pin.objects.all(), limit=limit)
        self.stdout.write(self.style.SUCCESS(f'Pins publiés : {n} (limite {limit}).'))
