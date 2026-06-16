"""Email J+7 inactif — créateurs suivis ont publié X fotos."""
from django.core.management.base import BaseCommand

from accounts.retention_services import run_j7_reactivation_emails


class Command(BaseCommand):
    help = 'Envoie les emails de réactivation J+7 (créateurs suivis).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=2000)

    def handle(self, *args, **options):
        result = run_j7_reactivation_emails(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(f"Done: {result}"))
