"""Compression sécurisée des images attachées aux commentaires."""

from __future__ import annotations

import logging

from django.core.files.uploadedfile import UploadedFile

from .upload_security import secure_image_upload

logger = logging.getLogger(__name__)


def compress_comment_media_upload(uploaded_file: UploadedFile, *, request=None, user_id: int | None = None) -> UploadedFile:
    """
    Valide (magic bytes, taille, anti-polyglot) puis re-encode via Pillow (EXIF retiré).
    """
    try:
        return secure_image_upload(
            uploaded_file,
            kind='comment',
            request=request,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning('Comment media secure pipeline failed: %s', exc)
        raise
