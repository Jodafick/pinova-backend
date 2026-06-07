"""Liste les vues API AllowAny sans throttling explicite ou par défaut."""

from django.core.management.base import BaseCommand

from pinova_backend.security.permissions_audit import (
    collect_allow_any_missing_throttle,
    collect_public_endpoints,
)


class Command(BaseCommand):
    help = 'Audit des endpoints API publics (AllowAny) sans throttle.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all-public',
            action='store_true',
            help='Afficher tous les endpoints AllowAny (pas seulement sans throttle).',
        )
        parser.add_argument(
            '--fail-on-findings',
            action='store_true',
            help='Code de sortie 1 si des endpoints AllowAny sans throttle sont trouvés.',
        )

    def handle(self, *args, **options):
        if options['all_public']:
            rows = collect_public_endpoints()
            self.stdout.write(self.style.MIGRATE_HEADING('Endpoints API AllowAny'))
        else:
            rows = collect_allow_any_missing_throttle()
            self.stdout.write(self.style.MIGRATE_HEADING('AllowAny SANS throttle'))

        if not rows:
            self.stdout.write(self.style.SUCCESS('Aucun endpoint concerné.'))
            return

        for row in rows:
            perms = ', '.join(row.permission_classes) or '-'
            throttles = ', '.join(row.throttle_classes) or '(aucun)'
            self.stdout.write(
                f"{row.route}\n"
                f"  view={row.view_name}\n"
                f"  permissions={perms}\n"
                f"  throttles={throttles}\n"
            )

        if options['fail_on_findings'] and not options['all_public']:
            self.stderr.write(
                self.style.ERROR(
                    f'{len(rows)} endpoint(s) AllowAny sans throttle — '
                    'revoir throttle_classes ou documenter (ex. webhook).'
                )
            )
            raise SystemExit(1)
