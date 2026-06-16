"""Cron : pré-chauffe discover page 1 (cache global TTL 120s)."""

from django.core.management.base import BaseCommand

from fotos.feed_cache import DISCOVER_PAGE1_TTL, warm_discover_page1_cache


class Command(BaseCommand):
    help = 'Pré-chauffe le cache discover page 1 (global, TTL 120s). À planifier toutes les ~90s.'

    def add_arguments(self, parser):
        parser.add_argument('--topic', default='', help='Filtre topic optionnel')
        parser.add_argument('--page-size', type=int, default=10)

    def handle(self, *args, **options):
        topic = (options.get('topic') or '').strip()
        page_size = max(1, min(int(options['page_size']), 100))
        key = warm_discover_page1_cache(topic=topic, page_size=page_size)
        self.stdout.write(
            self.style.SUCCESS(
                f'Discover page 1 warmed: key={key} ttl={DISCOVER_PAGE1_TTL}s topic={topic or "all"}'
            )
        )
