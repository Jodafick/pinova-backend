from django.core.management.base import BaseCommand

from referrals.models import ReferralAttribution
from referrals.services import grant_retention_bonus_if_eligible


class Command(BaseCommand):
    help = 'Attribue les bonus rétention referral (filleuls actifs après 7 j). À planifier en cron (ex. quotidien).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=2000)

    def handle(self, *args, **options):
        limit = max(1, min(int(options['limit'] or 2000), 20_000))
        qs = (
            ReferralAttribution.objects.filter(status=ReferralAttribution.STATUS_ACTIVE)
            .select_related('referee', 'referrer')
            .order_by('activated_at')[:limit]
        )
        n = 0
        for attr in qs:
            if grant_retention_bonus_if_eligible(attr):
                n += 1
        self.stdout.write(self.style.SUCCESS(f'Retention bonuses granted: {n}'))
