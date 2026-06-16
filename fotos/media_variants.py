"""Génération des variantes média (thumbnails feed, etc.)."""

from __future__ import annotations

import logging
import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction

from .models import Foto, FotoVariant
from .storage_media import unlink_field_file

logger = logging.getLogger('fotoce.media.variants')

FEED_THUMB_MAX_SIDE = 400
FEED_THUMB_JPEG_QUALITY = 82

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[misc, assignment]


def _lanczos():
    if not Image:
        return 1
    return getattr(Image, 'Resampling', Image).LANCZOS


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode in ('RGBA', 'LA'):
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    if im.mode != 'RGB':
        return im.convert('RGB')
    return im


def _encode_feed_jpeg(im: Image.Image) -> bytes:
    work = _to_rgb(im)
    work.thumbnail((FEED_THUMB_MAX_SIDE, FEED_THUMB_MAX_SIDE), _lanczos())
    buf = BytesIO()
    work.save(buf, format='JPEG', quality=FEED_THUMB_JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def ensure_foto_feed_thumbnail(foto: Foto, *, force: bool = False) -> FotoVariant | None:
    """
    Crée ou met à jour la variante `feed` (max 400px, ratio conservé) pour la grille.
    Retourne None si pas d'image source ou Pillow indisponible.
    """
    if Image is None:
        return None
    if not foto.image or not getattr(pin.image, 'name', ''):
        return None

    existing = (
        FotoVariant.objects.filter(foto=pin, kind=FotoVariant.KIND_FEED)
        .select_related('foto')
        .first()
    )
    if existing and not force:
        try:
            src_mtime = foto.image.storage.get_modified_time(pin.image.name).timestamp()
            var_mtime = existing.image.storage.get_modified_time(existing.image.name).timestamp()
            if var_mtime >= src_mtime:
                return existing
        except Exception:
            pass

    try:
        with foto.image.open('rb') as fh:
            im = Image.open(fh)
            im.load()
        payload = _encode_feed_jpeg(im)
    except Exception as exc:
        logger.warning('feed_thumbnail_failed foto=%s: %s', foto.pk, exc)
        return None

    filename = f'feed_{pin.pk}_{uuid.uuid4().hex[:10]}.jpg'
    content = ContentFile(payload, name=filename)

    with transaction.atomic():
        variant = existing
        if variant is None:
            variant = FotoVariant(foto=pin, kind=FotoVariant.KIND_FEED)
        elif variant.image and variant.image.name:
            unlink_field_file(variant.image)
        variant.image.save(filename, content, save=False)
        variant.save()

    return variant
