"""
Vue agrégée FAQ : entrées éditoriales + cartes dérivées des pages LegalDocument (privacy, terms, contact).
"""

from __future__ import annotations

from typing import Any

from .legal_page_i18n import build_legal_api_response, normalize_legal_lang
from .models import FaqItem, LegalDocument

LEGAL_SLUGS_ORDER = (
    LegalDocument.SLUG_PRIVACY,
    LegalDocument.SLUG_TERMS,
    LegalDocument.SLUG_CONTACT,
)


def _excerpt_plain(body: str, max_len: int = 190) -> str:
    raw = (body or '').replace('\r', '\n').strip()
    if not raw:
        return ''
    first_block = raw.split('\n\n', 1)[0].strip()
    line = ' '.join(first_block.split())
    if len(line) <= max_len:
        return line
    cut = line[:max_len].rsplit(' ', 1)[0]
    if len(cut) < 40:
        cut = line[:max_len]
    return f'{cut}…'


def build_faq_overview_response(lang_raw: str | None) -> dict[str, Any]:
    lang = normalize_legal_lang(lang_raw)
    use_en_primary = lang == 'en'

    items_out: list[dict[str, Any]] = []
    for row in FaqItem.objects.filter(is_published=True).order_by('sort_order', 'id'):
        q_fr = (row.question_fr or '').strip()
        q_en = (row.question_en or '').strip()
        a_fr = (row.answer_fr or '').strip()
        a_en = (row.answer_en or '').strip()
        if use_en_primary:
            question = q_en or q_fr
            answer = a_en or a_fr
        else:
            question = q_fr or q_en
            answer = a_fr or a_en
        rel = (row.related_legal_slug or '').strip()
        if rel not in (LegalDocument.SLUG_PRIVACY, LegalDocument.SLUG_TERMS, LegalDocument.SLUG_CONTACT):
            rel = ''
        items_out.append(
            {
                'id': row.id,
                'question': question,
                'answer': answer,
                'related_legal_slug': rel or None,
            }
        )

    legal_cards: list[dict[str, Any]] = []
    for slug in LEGAL_SLUGS_ORDER:
        full = build_legal_api_response(slug, lang)
        card: dict[str, Any] = {
            'slug': full['slug'],
            'title': full['title'],
            'excerpt': _excerpt_plain(full.get('body') or ''),
            'updated_at': full.get('updated_at'),
        }
        if slug == LegalDocument.SLUG_CONTACT:
            card['contact_email'] = full.get('contact_email')
        legal_cards.append(card)

    return {
        'lang': lang,
        'items': items_out,
        'legal_cards': legal_cards,
    }
