"""Compression des images attachées aux commentaires (Pillow)."""

from __future__ import annotations

import logging
import uuid
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageSequence
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[misc, assignment]
    ImageSequence = None  # type: ignore[misc, assignment]

# Qualité réduite pour limiter stockage / bande passante (affichage petit dans l’UI)
MAX_COMMENT_JPEG_SIDE = 1280
MAX_COMMENT_GIF_SIDE = 720
JPEG_QUALITY = 72


def _safe_name(prefix: str, ext: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}.{ext}'


def _lanczos_resample():
    if not Image:
        return 1
    return getattr(Image, 'Resampling', Image).LANCZOS


def compress_comment_media_upload(uploaded_file: UploadedFile) -> UploadedFile:
    """
    Compresse une image envoyée en commentaire.
    JPEG/PNG/WebP → JPEG optimisé ; GIF animé → redimensionnement + optimize.
    En cas d’échec, renvoie le fichier d’origine (repéré au début du flux).
    """
    if Image is None:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

    content_type = (getattr(uploaded_file, 'content_type', '') or '').split(';')[0].strip().lower()

    try:
        uploaded_file.seek(0)
        im = Image.open(uploaded_file)
        im.load()
        fmt = (im.format or '').upper()
    except Exception as exc:
        logger.warning('Comment media: open failed, using original (%s)', exc)
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

    try:
        if fmt == 'GIF' or content_type == 'image/gif':
            out = _compress_gif(im, uploaded_file.name)
        else:
            out = _compress_raster_to_jpeg(im, uploaded_file.name)
        if out is not None:
            return out
    except Exception as exc:
        logger.warning('Comment media: compress failed, using original (%s)', exc)

    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return uploaded_file


def _compress_raster_to_jpeg(im: Image.Image, original_name: str) -> InMemoryUploadedFile | None:
    work = im
    if work.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', work.size, (255, 255, 255))
        background.paste(work, mask=work.split()[-1])
        work = background
    elif work.mode == 'P':
        work = work.convert('RGBA')
        background = Image.new('RGB', work.size, (255, 255, 255))
        background.paste(work, mask=work.split()[-1])
        work = background
    elif work.mode != 'RGB':
        work = work.convert('RGB')

    work.thumbnail((MAX_COMMENT_JPEG_SIDE, MAX_COMMENT_JPEG_SIDE), _lanczos_resample())
    buf = BytesIO()
    work.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    buf.seek(0)
    size = buf.getbuffer().nbytes
    name = _safe_name('comment', 'jpg')
    return InMemoryUploadedFile(buf, 'media', name, 'image/jpeg', size, None)


def _compress_gif(im: Image.Image, original_name: str) -> InMemoryUploadedFile | None:
    if ImageSequence is None:
        return None

    frames: list[Image.Image] = []
    durations: list[int] = []

    try:
        for frame in ImageSequence.Iterator(im):
            rgba = frame.convert('RGBA')
            rgba.thumbnail((MAX_COMMENT_GIF_SIDE, MAX_COMMENT_GIF_SIDE), _lanczos_resample())
            frames.append(rgba)
            durations.append(int(frame.info.get('duration', im.info.get('duration', 100)) or 100))
    except Exception:
        return None

    if not frames:
        return None

    buf = BytesIO()
    loop = im.info.get('loop', 0)
    durs = durations[: len(frames)]
    if len(frames) > 1:
        frames[0].save(
            buf,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            duration=durs,
            loop=loop,
            optimize=True,
        )
    else:
        frames[0].save(buf, format='GIF', optimize=True)

    buf.seek(0)
    size = buf.getbuffer().nbytes
    name = _safe_name('comment', 'gif')
    return InMemoryUploadedFile(buf, 'media', name, 'image/gif', size, None)
