"""Modération serveur : profanité (better-profanity), rate limits (cache), flood identique."""

from __future__ import annotations

import hashlib
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from rest_framework import serializers

try:
    from better_profanity import profanity
except ImportError:
    profanity = None

MSG_PROFANITY = getattr(
    settings,
    'MODERATION_MSG_PROFANITY',
    'Ce contenu semble inapproprié. Merci de modifier votre texte.',
)
MSG_RATE = getattr(
    settings,
    'MODERATION_MSG_RATE',
    'Trop de publications dans un court laps de temps. Réessayez plus tard.',
)
MSG_FLOOD = getattr(
    settings,
    'MODERATION_MSG_FLOOD',
    'Vous avez envoyé trop de fois le même contenu très rapidement. Patientez un instant.',
)

RATE_PIN_PER_HOUR = getattr(settings, 'MODERATION_RATE_PIN_PER_HOUR', 15)
RATE_STORY_WINDOW_SEC = getattr(settings, 'MODERATION_RATE_STORY_WINDOW_SEC', 300)
RATE_STORY_MAX = getattr(settings, 'MODERATION_RATE_STORY_MAX', 5)
RATE_COMMENT_PER_MINUTE = getattr(settings, 'MODERATION_RATE_COMMENT_PER_MINUTE', 10)

FLOOD_WINDOW_SEC = getattr(settings, 'MODERATION_FLOOD_WINDOW_SEC', 60)
FLOOD_MAX_IDENTICAL = getattr(settings, 'MODERATION_FLOOD_MAX_IDENTICAL', 15)

REPORTS_NEED_REVIEW = getattr(settings, 'MODERATION_REPORTS_NEED_REVIEW', 2)
REPORTS_HIDE = getattr(settings, 'MODERATION_REPORTS_HIDE', 5)


def _consume_fixed_window(user_id: int, bucket: str, limit: int, window_seconds: int) -> None:
    slot = int(time.time()) // window_seconds
    key = f'pinova_rl:{bucket}:{user_id}:{slot}'
    n = cache.get(key, 0)
    if n >= limit:
        raise serializers.ValidationError(MSG_RATE)
    cache.set(key, n + 1, timeout=window_seconds + 5)


def apply_pin_creation_rate_limits(user_id: int, is_story: bool) -> None:
    """Pins : 15/h ; stories en plus : 5 / 5 minutes (anti-bot / flood publication)."""
    _consume_fixed_window(user_id, 'pin_hour', RATE_PIN_PER_HOUR, 3600)
    if is_story:
        _consume_fixed_window(user_id, 'story_burst', RATE_STORY_MAX, RATE_STORY_WINDOW_SEC)


def apply_comment_rate_limit(user_id: int) -> None:
    _consume_fixed_window(user_id, 'comment_min', RATE_COMMENT_PER_MINUTE, 60)


def normalize_snippet(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def pin_body_fingerprint(title: str, description: str) -> str:
    raw = normalize_snippet(title) + '\x00' + normalize_snippet(description)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:48]


def comment_body_fingerprint(text: str, gif_url: str | None) -> str:
    raw = normalize_snippet(text) + '\x00' + normalize_snippet(gif_url or '')
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:48]


def enforce_identical_content_flood(user_id: int, kind: str, fingerprint: str) -> None:
    """Même contenu renvoyé trop souvent dans une fenêtre courte (bots)."""
    slot = int(time.time()) // FLOOD_WINDOW_SEC
    key = f'pinova_flood:{kind}:{user_id}:{fingerprint}:{slot}'
    n = cache.get(key, 0)
    if n >= FLOOD_MAX_IDENTICAL:
        raise serializers.ValidationError(MSG_FLOOD)
    cache.set(key, n + 1, timeout=FLOOD_WINDOW_SEC + 5)


def validate_text_profanity(*chunks: str) -> None:
    if not profanity:
        return
    for chunk in chunks:
        if chunk and profanity.contains_profanity(chunk):
            raise serializers.ValidationError(MSG_PROFANITY)


def validate_pin_text(title: str, description: str, public_tags: list[str] | None = None) -> None:
    validate_text_profanity(title or '', description or '')
    if public_tags:
        validate_text_profanity(' '.join(public_tags))


def validate_comment_text(text: str) -> None:
    validate_text_profanity(text or '')


def pin_is_story_flag(raw_is_story, validated_is_story) -> bool:
    if validated_is_story is True:
        return True
    return str(raw_is_story).lower() in ('true', '1', 'yes')


def apply_pin_report_thresholds(pin) -> None:
    from .models import Pin

    updates = {}
    if pin.report_count >= REPORTS_HIDE:
        updates['moderation_hidden'] = True
        updates['needs_review'] = True
    elif pin.report_count >= REPORTS_NEED_REVIEW:
        updates['needs_review'] = True
    if updates:
        Pin.objects.filter(pk=pin.pk).update(**updates)


def apply_comment_report_thresholds(comment) -> None:
    from .models import Comment

    updates = {}
    if comment.report_count >= REPORTS_HIDE:
        updates['moderation_hidden'] = True
        updates['needs_review'] = True
    elif comment.report_count >= REPORTS_NEED_REVIEW:
        updates['needs_review'] = True
    if updates:
        Comment.objects.filter(pk=comment.pk).update(**updates)


def increment_pin_reports(pin_id: int) -> None:
    from .models import Pin

    Pin.objects.filter(pk=pin_id).update(report_count=F('report_count') + 1)


def increment_comment_reports(comment_id: int) -> None:
    from .models import Comment

    Comment.objects.filter(pk=comment_id).update(report_count=F('report_count') + 1)
