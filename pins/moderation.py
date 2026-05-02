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

MSG_PROFANITY_TITLE = getattr(
    settings,
    'MODERATION_MSG_PROFANITY_TITLE',
    'Votre titre semble inapproprié. Merci de le modifier.',
)
MSG_PROFANITY_DESCRIPTION = getattr(
    settings,
    'MODERATION_MSG_PROFANITY_DESCRIPTION',
    'Votre description semble inappropriée. Merci de la modifier.',
)
MSG_PROFANITY_TAGS_PUBLIC = getattr(
    settings,
    'MODERATION_MSG_PROFANITY_TAGS_PUBLIC',
    'Vos tags publics semblent inappropriés. Merci de les modifier.',
)
MSG_PROFANITY_TAGS_PRIVATE = getattr(
    settings,
    'MODERATION_MSG_PROFANITY_TAGS_PRIVATE',
    'Vos tags privés semblent inappropriés. Merci de les modifier.',
)
MSG_PROFANITY_COMMENT = getattr(
    settings,
    'MODERATION_MSG_PROFANITY_COMMENT',
    'Votre commentaire semble inapproprié. Merci de le modifier.',
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


def _profanity_in(text: str) -> bool:
    return bool(text and profanity and profanity.contains_profanity(text))


def validate_pin_text(
    title: str,
    description: str,
    public_tags: list[str] | None = None,
    private_tags: list[str] | None = None,
) -> None:
    """Lève ValidationError avec une clé par champ (compatibles avec le serializer)."""
    if not profanity:
        return
    errors: dict[str, list[str]] = {}
    if _profanity_in(title or ''):
        errors['title'] = [MSG_PROFANITY_TITLE]
    if _profanity_in(description or ''):
        errors['description'] = [MSG_PROFANITY_DESCRIPTION]
    pub_joined = ' '.join(public_tags) if public_tags else ''
    if _profanity_in(pub_joined):
        errors['public_tags_input'] = [MSG_PROFANITY_TAGS_PUBLIC]
    priv_joined = ' '.join(private_tags) if private_tags else ''
    if _profanity_in(priv_joined):
        errors['private_tags_input'] = [MSG_PROFANITY_TAGS_PRIVATE]
    if errors:
        raise serializers.ValidationError(errors)


def validate_comment_text(text: str) -> None:
    if not profanity:
        return
    if _profanity_in(text or ''):
        raise serializers.ValidationError({'text': [MSG_PROFANITY_COMMENT]})


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
