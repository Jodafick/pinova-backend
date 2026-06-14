"""URLs de livraison Cloudinary (f_auto / q_auto) pour les médias publics."""

from __future__ import annotations

import cloudinary.utils


def cloudinary_delivery_url(public_id: str) -> str:
    """URL HTTPS optimisée (format et qualité automatiques)."""
    url, _options = cloudinary.utils.cloudinary_url(
        public_id,
        secure=True,
        fetch_format='auto',
        quality='auto',
    )
    return url or ''
