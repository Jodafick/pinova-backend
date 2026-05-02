"""
Applique `_enforce_subscription_state` pour tous les profils dont la date
de renouvellement / fin de période est atteinte ou dépassée.

À planifier via cron (ex. toutes les 5–15 minutes) pour désactiver Plus/Pro
sans attendre qu’un utilisateur appelle l’API.

Exemple crontab :
  */10 * * * * cd /path/pinova-backend && .venv/bin/python manage.py enforce_subscriptions_due
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Profile
from accounts.subscription_utils import _enforce_subscription_state


class Command(BaseCommand):
    help = (
        'Pour les profils avec subscription_renewal_at <= maintenant, '
        'applique le plan programmé ou la réversion en Free (annulation à l’échéance).'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = Profile.objects.filter(subscription_renewal_at__isnull=False, subscription_renewal_at__lte=now)
        total_scanned = qs.count()
        updated = 0

        for pk in qs.values_list('pk', flat=True).iterator(chunk_size=500):
            profile = Profile.objects.select_related('user').get(pk=pk)
            if _enforce_subscription_state(profile):
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'enforce_subscriptions_due: scanned={total_scanned}, profiles_updated={updated}, as_of={now.isoformat()}'
            )
        )
