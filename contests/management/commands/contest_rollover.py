from django.core.management.base import BaseCommand
from django.utils import timezone

from contests.models import ContestSettings
from contests.services import create_monthly_contest_if_missing, finalize_contest
from referrals.referral_contest_monthly import finalize_referral_month_for_contest


class Command(BaseCommand):
    help = 'Finalize ended monthly contests and bootstrap current month contest.'

    def handle(self, *args, **options):
        now = timezone.now()
        ended = ContestSettings.objects.filter(end_at__lte=now, is_locked=False)
        for contest in ended:
            finalize_contest(contest)
            finalize_referral_month_for_contest(contest)
            contest.is_locked = True
            contest.is_active = False
            contest.save(update_fields=['is_locked', 'is_active', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(f'Contest finalized: {contest.contest_key}'))

        current = create_monthly_contest_if_missing(now=now)
        if not current.is_active:
            current.is_active = True
            current.save(update_fields=['is_active', 'updated_at'])
        self.stdout.write(self.style.SUCCESS(f'Current contest active: {current.contest_key}'))
