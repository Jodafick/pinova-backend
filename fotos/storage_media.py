"""Supprime physiquement les fichiers média sur le backend (pas seulement le champ Django)."""

from typing import Optional


def unlink_named(storage, name: Optional[str]) -> None:
    if not storage or not (name or '').strip():
        return
    try:
        storage.delete(name)
    except Exception:
        # S3 hors-ligne, fichier déjà absent, etc.
        pass


def unlink_field_file(field_file) -> None:
    if not field_file:
        return
    name = getattr(field_file, 'name', '') or ''
    unlink_named(getattr(field_file, 'storage', None), name)
