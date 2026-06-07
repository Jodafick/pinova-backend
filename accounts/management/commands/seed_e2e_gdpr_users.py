"""Comptes vérifiés pour les tests Playwright RGPD (local / staging e2e)."""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.password_policy import PASSWORD_VALID_EXAMPLE
from accounts.models import DataExportJob

try:
    from allauth.account.models import EmailAddress
except ImportError:  # pragma: no cover
    EmailAddress = None

E2E_PASSWORD = PASSWORD_VALID_EXAMPLE

E2E_USERS = (
    {
        'email': 'gdpr.export@pinova.test',
        'username': 'gdpr_export',
        'birth_date': date(1995, 3, 15),
    },
    {
        'email': 'gdpr.delete@pinova.test',
        'username': 'gdpr_delete',
        'birth_date': date(1992, 7, 20),
    },
    {
        'email': 'gdpr.teen@pinova.test',
        'username': 'gdpr_teen',
        'birth_date': date.today().replace(year=date.today().year - 14),
    },
)


def _ensure_verified_email(user: User) -> None:
    if EmailAddress is None:
        return
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email.lower(),
        defaults={'primary': True, 'verified': True},
    )


class Command(BaseCommand):
    help = 'Crée ou met à jour les comptes e2e RGPD (Playwright, mot de passe Pinova2026).'

    def handle(self, *args, **options):
        now = timezone.now()
        for spec in E2E_USERS:
            user, created = User.objects.get_or_create(
                email=spec['email'],
                defaults={'username': spec['username']},
            )
            user.username = spec['username']
            user.set_password(E2E_PASSWORD)
            user.is_active = True
            user.save()

            profile = user.profile
            profile.birth_date = spec['birth_date']
            profile.onboarding_completed_at = profile.onboarding_completed_at or now
            profile.account_scheduled_deletion_at = None
            profile.save(
                update_fields=[
                    'birth_date',
                    'onboarding_completed_at',
                    'account_scheduled_deletion_at',
                ],
            )

            deleted, _ = DataExportJob.objects.filter(user=user).delete()
            if deleted:
                self.stdout.write(f'  -> {deleted} export(s) purges pour {spec["email"]}')

            _ensure_verified_email(user)
            action = 'cree' if created else 'mis a jour'
            self.stdout.write(self.style.SUCCESS(f'{spec["email"]} {action}'))

        self.stdout.write(f'Mot de passe e2e : {E2E_PASSWORD}')
