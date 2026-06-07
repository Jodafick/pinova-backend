from django.core.management.base import BaseCommand

from referrals.models import ReferralAttribution
from referrals.services import try_complete_referral_rewards


class Command(BaseCommand):
    help = (
        'Finalise les récompenses referral en attente (anti-fraude). '
        'Production : Celery Beat referrals-reward-scan (*/15 min). '
        'Secours : manage.py referral_reward_scan'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=3000)

    def handle(self, *args, **options):
        limit = max(1, min(int(options['limit'] or 3000), 50_000))
        qs = (
            ReferralAttribution.objects.filter(
                status=ReferralAttribution.STATUS_ACTIVE,
                rewards_granted_at__isnull=True,
            )
            .select_related('referee', 'referrer')
            .order_by('created_at')[:limit]
        )
        granted = 0
        for attr in qs:
            if try_complete_referral_rewards(attr) == 'granted':
                granted += 1
        self.stdout.write(self.style.SUCCESS(f'Referral rewards scan done; newly granted: {granted}'))
