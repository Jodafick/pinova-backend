"""Génère les variantes feed (400px) pour les fotos existants."""

from django.core.management.base import BaseCommand

from fotos.media_variants import ensure_foto_feed_thumbnail
from fotos.models import Foto


class Command(BaseCommand):
    help = 'Crée les thumbnails feed (FotoVariant KIND_FEED) pour les fotos avec image.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max fotos (0 = tous)')
        parser.add_argument('--force', action='store_true', help='Régénère même si déjà présent')

    def handle(self, *args, **options):
        qs = Foto.objects.exclude(image='').order_by('-id')
        limit = int(options['limit'] or 0)
        if limit > 0:
            qs = qs[:limit]
        force = bool(options['force'])
        ok = skip = err = 0
        for foto in qs.iterator(chunk_size=100):
            try:
                variant = ensure_foto_feed_thumbnail(pin, force=force)
                if variant:
                    ok += 1
                else:
                    skip += 1
            except Exception as exc:
                err += 1
                self.stderr.write(f'pin {pin.pk}: {exc}')
        self.stdout.write(self.style.SUCCESS(f'done ok={ok} skip={skip} err={err}'))
