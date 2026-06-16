"""Validation uploads — magic bytes, anti-polyglot, re-encodage Pillow, scan ClamAV optionnel."""

from __future__ import annotations

import logging
import os
import uuid
from io import BytesIO
from typing import Literal

import filetype
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from rest_framework import serializers

logger = logging.getLogger('fotoce.upload.security')

UploadKind = Literal['foto', 'avatar', 'cover', 'comment']

CODE_IMAGE_INVALID = 'upload.image.invalid_type'
CODE_IMAGE_POLYGLOT = 'upload.image.polyglot'
CODE_IMAGE_TOO_LARGE = 'upload.image.too_large'
CODE_VIDEO_INVALID = 'upload.video.invalid_type'
CODE_VIDEO_POLYGLOT = 'upload.video.polyglot'
CODE_PROCESSING_FAILED = 'upload.processing_failed'

IMAGE_MIME_BY_EXT = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}

VIDEO_MIME_BY_EXT = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.mov': 'video/quicktime',
}

ALLOWED_IMAGE_MIMES = frozenset(IMAGE_MIME_BY_EXT.values())
ALLOWED_VIDEO_MIMES = frozenset(VIDEO_MIME_BY_EXT.values())

try:
    from PIL import Image, ImageSequence
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[misc, assignment]
    ImageSequence = None  # type: ignore[misc, assignment]

_KIND_MAX_SIDE = {
    'pin': 4096,
    'avatar': 1024,
    'cover': 2560,
    'comment': 1280,
}


def image_max_bytes() -> int:
    mb = float(getattr(settings, 'PIN_IMAGE_MAX_SIZE_MB', 10) or 10)
    return int(round(max(mb, 1) * 1024 * 1024))


def _raise_upload_error(code: str, request=None, **fmt) -> None:
    raise serializers.ValidationError(code)


def _safe_name(prefix: str, ext: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}.{ext}'


def _lanczos_resample():
    if not Image:
        return 1
    return getattr(Image, 'Resampling', Image).LANCZOS


def _read_header(uploaded: UploadedFile, size: int = 261) -> bytes:
    uploaded.seek(0)
    head = uploaded.read(size)
    uploaded.seek(0)
    return head or b''


def _extension_of(uploaded: UploadedFile) -> str:
    name = (getattr(uploaded, 'name', '') or '').strip().lower()
    _, ext = os.path.splitext(name)
    return ext if ext in IMAGE_MIME_BY_EXT or ext in VIDEO_MIME_BY_EXT else ''


def _declared_content_type(uploaded: UploadedFile) -> str:
    return (getattr(uploaded, 'content_type', '') or '').split(';')[0].strip().lower()


def _detect_mime(head: bytes) -> str | None:
    kind = filetype.guess(head)
    if kind is None:
        return None
    mime = (kind.mime or '').strip().lower()
    if mime == 'image/jpg':
        return 'image/jpeg'
    return mime or None


def _reject_polyglot(
    uploaded: UploadedFile,
    *,
    detected_mime: str,
    allowed_ext_map: dict[str, str],
    allowed_mimes: frozenset[str],
    code: str,
    request=None,
) -> None:
    ext = _extension_of(uploaded)
    if ext and ext in allowed_ext_map and allowed_ext_map[ext] != detected_mime:
        _raise_upload_error(code, request)
    declared = _declared_content_type(uploaded)
    if declared and declared in allowed_mimes and declared != detected_mime:
        _raise_upload_error(code, request)


def validate_image_magic_bytes(uploaded: UploadedFile, request=None) -> str:
    head = _read_header(uploaded)
    detected = _detect_mime(head)
    if detected not in ALLOWED_IMAGE_MIMES:
        _raise_upload_error(CODE_IMAGE_INVALID, request)
    _reject_polyglot(
        uploaded,
        detected_mime=detected,
        allowed_ext_map=IMAGE_MIME_BY_EXT,
        allowed_mimes=ALLOWED_IMAGE_MIMES,
        code=CODE_IMAGE_POLYGLOT,
        request=request,
    )
    return detected


def validate_video_magic_bytes(uploaded: UploadedFile, request=None) -> str:
    head = _read_header(uploaded, size=4096)
    detected = _detect_mime(head)
    if detected == 'video/quicktime':
        pass
    elif detected == 'application/mp4':
        detected = 'video/mp4'
    elif detected not in ALLOWED_VIDEO_MIMES:
        _raise_upload_error(CODE_VIDEO_INVALID, request)
    _reject_polyglot(
        uploaded,
        detected_mime=detected,
        allowed_ext_map=VIDEO_MIME_BY_EXT,
        allowed_mimes=ALLOWED_VIDEO_MIMES,
        code=CODE_VIDEO_POLYGLOT,
        request=request,
    )
    return detected


def validate_image_size(uploaded: UploadedFile, request=None) -> None:
    max_bytes = image_max_bytes()
    size = int(getattr(uploaded, 'size', 0) or 0)
    if size > max_bytes:
        _raise_upload_error(
            CODE_IMAGE_TOO_LARGE,
            request,
            max_mb=float(getattr(settings, 'PIN_IMAGE_MAX_SIZE_MB', 10) or 10),
        )


def _to_rgb_canvas(im: Image.Image) -> Image.Image:
    if im.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', im.size, (255, 255, 255))
        background.paste(im, mask=im.split()[-1])
        return background
    if im.mode == 'P':
        rgba = im.convert('RGBA')
        background = Image.new('RGB', rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if im.mode != 'RGB':
        return im.convert('RGB')
    return im


def _reencode_gif(im: Image.Image, *, max_side: int, prefix: str) -> InMemoryUploadedFile:
    if ImageSequence is None:
        _raise_upload_error(CODE_PROCESSING_FAILED)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for frame in ImageSequence.Iterator(im):
        rgba = frame.convert('RGBA')
        rgba.thumbnail((max_side, max_side), _lanczos_resample())
        frames.append(rgba)
        durations.append(int(frame.info.get('duration', im.info.get('duration', 100)) or 100))
    if not frames:
        _raise_upload_error(CODE_PROCESSING_FAILED)
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
    return InMemoryUploadedFile(buf, 'image', _safe_name(prefix, 'gif'), 'image/gif', size, None)


def _reencode_jpeg(im: Image.Image, *, max_side: int, prefix: str, quality: int) -> InMemoryUploadedFile:
    work = _to_rgb_canvas(im)
    work.thumbnail((max_side, max_side), _lanczos_resample())
    buf = BytesIO()
    work.save(buf, format='JPEG', quality=quality, optimize=True)
    buf.seek(0)
    size = buf.getbuffer().nbytes
    return InMemoryUploadedFile(buf, 'image', _safe_name(prefix, 'jpg'), 'image/jpeg', size, None)


def reencode_image_upload(uploaded: UploadedFile, *, kind: UploadKind) -> InMemoryUploadedFile:
    if Image is None:
        _raise_upload_error(CODE_PROCESSING_FAILED)
    uploaded.seek(0)
    try:
        im = Image.open(uploaded)
        im.load()
        fmt = (im.format or '').upper()
    except Exception as exc:
        logger.warning('upload_reencode_open_failed: %s', exc)
        _raise_upload_error(CODE_PROCESSING_FAILED)
    max_side = _KIND_MAX_SIDE.get(kind, 4096)
    quality = int(getattr(settings, 'PIN_IMAGE_JPEG_QUALITY', 85) or 85)
    prefix = {'pin': 'pin', 'avatar': 'avatar', 'cover': 'cover', 'comment': 'comment'}.get(kind, 'media')
    if fmt == 'GIF' or _declared_content_type(uploaded) == 'image/gif':
        return _reencode_gif(im, max_side=max_side, prefix=prefix)
    return _reencode_jpeg(im, max_side=max_side, prefix=prefix, quality=quality)


def schedule_upload_clamav_scan(uploaded: UploadedFile, *, media_kind: str, user_id: int | None) -> None:
    if not getattr(settings, 'ENABLE_CLAMAV_SCAN', False):
        return
    try:
        from .clamav_scan import enqueue_clamav_scan

        uploaded.seek(0)
        payload = uploaded.read()
        uploaded.seek(0)
        enqueue_clamav_scan(payload, media_kind=media_kind, user_id=user_id)
    except Exception as exc:
        logger.warning('clamav_schedule_skipped: %s', exc)


def secure_image_upload(
    uploaded: UploadedFile,
    *,
    kind: UploadKind,
    request=None,
    user_id: int | None = None,
) -> UploadedFile:
    validate_image_size(uploaded, request=request)
    validate_image_magic_bytes(uploaded, request=request)
    reencoded = reencode_image_upload(uploaded, kind=kind)
    schedule_upload_clamav_scan(reencoded, media_kind=kind, user_id=user_id)
    return reencoded


def secure_video_upload(
    uploaded: UploadedFile,
    *,
    request=None,
    user_id: int | None = None,
) -> UploadedFile:
    validate_video_magic_bytes(uploaded, request=request)
    uploaded.seek(0)
    schedule_upload_clamav_scan(uploaded, media_kind='video', user_id=user_id)
    return uploaded
