"""Helpers pour réponses paginées des fils avec pubs partenaires."""

from __future__ import annotations

from monetization.services import interleave_partner_ads


def build_feed_paginated_response(viewset, request, page_items, topic: str = ''):
    """Sérialise une page de pins et injecte les pubs partenaire."""
    serializer = viewset.get_serializer(page_items, many=True)
    results = list(serializer.data)
    page_number = 1
    paginator = getattr(viewset, 'paginator', None)
    if paginator is not None and getattr(paginator, 'page', None) is not None:
        page_number = paginator.page.number
    results = interleave_partner_ads(request, results, topic=topic, page_number=page_number)
    return viewset.get_paginated_response(results)
