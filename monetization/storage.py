"""Stockage médias campagnes créateur (image ou vidéo selon l’extension)."""

from __future__ import annotations

from cloudinary_storage.storage import MediaCloudinaryStorage, RESOURCE_TYPES

VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov', '.m4v', '.mpeg', '.avi', '.mkv')


class CreatorAdMediaCloudinaryStorage(MediaCloudinaryStorage):
    """Cloudinary : resource_type video pour les fichiers vidéo (évite « Invalid image file »)."""

    def _get_resource_type(self, name):
        low = (name or '').lower()
        if any(low.endswith(ext) for ext in VIDEO_EXTENSIONS):
            return RESOURCE_TYPES['VIDEO']
        return RESOURCE_TYPES['IMAGE']


def creator_ad_media_storage():
    from django.conf import settings
    from django.core.files.storage import FileSystemStorage

    if getattr(settings, 'USE_CLOUDINARY_MEDIA', False):
        return CreatorAdMediaCloudinaryStorage()
    return FileSystemStorage(location=settings.MEDIA_ROOT)
