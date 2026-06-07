"""Email J+30 inactif — résumé mois + CTA concours/referral."""
from django.core.management.base import BaseCommand

from accounts.retention_services import run_j30_reactivation_emails


class Command(BaseCommand):
    help = 'Envoie les emails de réactivation J+30 (résumé + concours/referral).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=2000)

    def handle(self, *args, **options):
        result = run_j30_reactivation_emails(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(f"Done: {result}"))
