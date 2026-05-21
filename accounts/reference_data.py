"""Catalogue d'intérêts onboarding — source unique servie par l'API reference."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_INTERESTS_PATH = Path(__file__).resolve().parent / 'reference' / 'interests.json'


@lru_cache(maxsize=1)
def load_interests_catalog() -> list[dict]:
    with _INTERESTS_PATH.open(encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        return []
    return data


def get_allowed_interest_slugs() -> frozenset[str]:
    return frozenset(str(item.get('slug', '')).strip().lower() for item in load_interests_catalog() if item.get('slug'))


def normalize_interest_slugs(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith('['):
            try:
                parsed = json.loads(raw)
                raw = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        else:
            raw = [p.strip() for p in raw.split(',') if p.strip()]
    if not isinstance(raw, list):
        return []
    allowed = get_allowed_interest_slugs()
    out: list[str] = []
    for item in raw:
        slug = str(item).strip().lower()
        if slug and slug in allowed and slug not in out:
            out.append(slug)
    return out


def interest_catalog_for_lang(lang: str = 'fr') -> list[dict]:
    lang = (lang or 'fr').strip().lower()[:12]
    items = []
    for row in load_interests_catalog():
        slug = str(row.get('slug', '')).strip()
        if not slug:
            continue
        label = row.get('nameFr') or slug
        if lang == 'en':
            label = row.get('nameEn') or label
        elif lang == 'fon':
            label = row.get('nameFon') or row.get('nameFr') or label
        items.append({
            'slug': slug,
            'icon': row.get('icon') or 'category',
            'category': row.get('category') or 'general',
            'nameFr': row.get('nameFr') or slug,
            'nameEn': row.get('nameEn') or slug,
            'nameFon': row.get('nameFon') or row.get('nameFr') or slug,
            'label': label,
        })
    return items
