"""
Supprime les comptes dont la date account_scheduled_deletion_at est dépassée.

Production : Celery Beat `accounts-purge-deletions` (quotidien 03:00 UTC).
Secours : python manage.py purge_scheduled_account_deletions
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Profile


class Command(BaseCommand):
    help = (
        'Supprime les utilisateurs dont le profil porte account_scheduled_deletion_at <= maintenant.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = Profile.objects.filter(
            account_scheduled_deletion_at__isnull=False,
            account_scheduled_deletion_at__lte=now,
        ).select_related('user')
        deleted = 0
        for profile in qs.iterator(chunk_size=200):
            uid = profile.user_id
            User.objects.filter(pk=uid).delete()
            deleted += 1
        self.stdout.write(
            self.style.SUCCESS(
                f'purge_scheduled_account_deletions: deleted_users={deleted}, as_of={now.isoformat()}'
            )
        )
