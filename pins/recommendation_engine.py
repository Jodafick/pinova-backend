from __future__ import annotations

from collections import Counter
from datetime import timedelta
from math import sqrt
import re

from django.db.models import Count
from django.utils import timezone

from .models import (
    Like,
    Pin,
    PinEmbedding,
    PinViewEvent,
    Save,
    TagInvisible,
    UserEmbedding,
    UserInteraction,
)


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,40}")
EMBEDDING_DIM = 128


def _tokenize(*texts: str) -> list[str]:
    tokens: list[str] = []
    for raw in texts:
        txt = (raw or "").lower()
        if not txt:
            continue
        tokens.extend(TOKEN_RE.findall(txt))
    return tokens


def _vector_from_tokens(tokens: list[str], dim: int = EMBEDDING_DIM) -> list[float]:
    if not tokens:
        return [0.0] * dim
    counts = Counter(tokens)
    total = float(sum(counts.values()) or 1)
    vec = [0.0] * dim
    for token, c in counts.items():
        idx = hash(token) % dim
        vec[idx] += c / total
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = sqrt(sum(b[i] * b[i] for i in range(n)))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_pin_embedding(pin: Pin) -> list[float]:
    tokens = _tokenize(pin.title, pin.description, " ".join(pin.hashtags.values_list("name", flat=True)))
    return _vector_from_tokens(tokens)


def update_pin_ai_metadata(pin: Pin) -> None:
    vector = build_pin_embedding(pin)
    PinEmbedding.objects.update_or_create(
        pin=pin,
        defaults={"embedding": vector, "embedding_dim": len(vector)},
    )
    tokens = _tokenize(pin.title, pin.description)
    counts = Counter(tokens)
    total = float(sum(counts.values()) or 1)
    # Garde un petit top-k lisible, utilisé en fallback search / boost.
    top = counts.most_common(12)
    for tag, score_raw in top:
        TagInvisible.objects.update_or_create(
            pin=pin,
            tag=tag,
            defaults={"confidence": min(1.0, score_raw / total + 0.3)},
        )


def _interaction_weight(event_type: str) -> float:
    return {
        UserInteraction.TYPE_VIEW: 1.0,
        UserInteraction.TYPE_CLICK: 2.0,
        UserInteraction.TYPE_SAVE: 3.0,
        UserInteraction.TYPE_CREATOR_VISIT: 2.5,
        UserInteraction.TYPE_LIKE: 4.0,
    }.get(event_type, 1.0)


def update_user_embedding(user) -> None:
    recent = (
        UserInteraction.objects.filter(user=user)
        .select_related("pin")
        .order_by("-created_at")[:500]
    )
    if not recent:
        return
    accum = [0.0] * EMBEDDING_DIM
    weight_sum = 0.0
    for interaction in recent:
        if not interaction.pin_id:
            continue
        p_emb = getattr(interaction.pin, "embedding_profile", None)
        vec = p_emb.embedding if p_emb and p_emb.embedding else build_pin_embedding(interaction.pin)
        w = _interaction_weight(interaction.event_type) * max(1.0, interaction.dwell_seconds / 5.0)
        weight_sum += w
        for i in range(min(len(accum), len(vec))):
            accum[i] += vec[i] * w
    if weight_sum <= 0:
        return
    final = [v / weight_sum for v in accum]
    UserEmbedding.objects.update_or_create(
        user=user,
        defaults={"embedding": final, "embedding_dim": len(final)},
    )


def recommendation_score(pin: Pin, user, user_vector: list[float], followed_creator_ids: set[int]) -> float:
    emb_obj = getattr(pin, "embedding_profile", None)
    pin_vec = emb_obj.embedding if emb_obj and emb_obj.embedding else []
    similarity = max(0.0, cosine_similarity(user_vector, pin_vec))

    now = timezone.now()
    age_hours = max(1.0, (now - pin.created_at).total_seconds() / 3600.0)
    freshness = max(0.0, 1.0 - min(age_hours / (24.0 * 14.0), 1.0))

    popularity = min(1.0, (getattr(pin, "_likes_total", 0) * 0.6 + getattr(pin, "_saves_total", 0) * 0.4) / 200.0)
    engagement = min(1.0, (getattr(pin, "_views_total", 0) / 600.0))
    affinity = 1.0 if pin.author_id in followed_creator_ids else 0.0

    score = (
        similarity * 0.50
        + popularity * 0.15
        + freshness * 0.15
        + affinity * 0.10
        + engagement * 0.10
    )
    return score


def rank_recommendations_for_user(user, base_queryset):
    user_emb = UserEmbedding.objects.filter(user=user).first()
    user_vector = user_emb.embedding if user_emb and user_emb.embedding else []
    followed_creator_ids = set(user.profile.following.values_list("user_id", flat=True))
    qs = (
        base_queryset
        .annotate(
            _likes_total=Count("likes", distinct=True),
            _saves_total=Count("saves", distinct=True),
            _views_total=Count("view_events", distinct=True),
        )
        .select_related("embedding_profile")
        .order_by("-created_at")[:300]
    )
    items = list(qs)
    if not user_vector:
        # Fallback froid: popularité + fraîcheur.
        items.sort(
            key=lambda p: (
                getattr(p, "_likes_total", 0) + getattr(p, "_saves_total", 0) * 2 + getattr(p, "_views_total", 0) * 0.2,
                p.created_at,
            ),
            reverse=True,
        )
        return items
    items.sort(
        key=lambda p: recommendation_score(p, user, user_vector, followed_creator_ids),
        reverse=True,
    )
    return items
