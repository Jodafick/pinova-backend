"""Push J+1 si streak discovery à risque."""
from django.core.management.base import BaseCommand

from accounts.retention_services import run_discovery_streak_reminders


class Command(BaseCommand):
    help = 'Envoie les rappels push streak discovery (J+1 à risque).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=5000)

    def handle(self, *args, **options):
        result = run_discovery_streak_reminders(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(f"Done: {result}"))
