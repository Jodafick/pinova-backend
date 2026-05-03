"""
Textes canoniques français pour les notifications, puis traduction (googletrans)
vers la langue préférée du destinataire — même stratégie que pins.topic_i18n.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from googletrans import Translator
from asgiref.sync import async_to_sync

from pins.translation import translate_text_to
from pins.topic_i18n import SUPPORTED_TOPIC_LANGS


NOTIFICATION_TITLE_MAX = 120
NOTIFICATION_MESSAGE_MAX = 255


def recipient_language(user: User) -> str:
    try:
        profile = getattr(user, 'profile', None)
        raw = (getattr(profile, 'preferred_language', None) or 'fr').strip().lower().split('-')[0]
    except Exception:
        return 'fr'
    if raw in SUPPORTED_TOPIC_LANGS:
        return raw
    return 'fr'


def localize_notification_strings(title_fr: str, body_fr: str, lang: str) -> tuple[str, str]:
    title_fr = title_fr[:NOTIFICATION_TITLE_MAX] if title_fr else ''
    body_raw = body_fr[:NOTIFICATION_MESSAGE_MAX] if body_fr else ''
    if lang == 'fr':
        return title_fr, body_raw
    translator = Translator()
    try:
        new_title = title_fr.strip() and async_to_sync(translate_text_to)(
            translator,
            title_fr.strip(),
            lang,
            'fr',
        ) or ''
        new_body = async_to_sync(translate_text_to)(
            translator,
            body_raw,
            lang,
            'fr',
        )
    except (RuntimeError, Exception):
        return title_fr, body_raw
    titled = new_title.strip()[:NOTIFICATION_TITLE_MAX] if new_title.strip() else title_fr
    bodied = (new_body or body_raw).strip()[:NOTIFICATION_MESSAGE_MAX]
    return titled or title_fr[:NOTIFICATION_TITLE_MAX], bodied or body_raw


def localized_pairs_for_recipient(title_fr: str, body_fr: str, recipient: User) -> tuple[str, str]:
    return localize_notification_strings(title_fr or '', body_fr or '', recipient_language(recipient))


def create_localized_notification(*, recipient: User, title_fr: str = '', message_fr: str, **notification_fields):
    """Notification.objects.create avec title/message adaptés au profil (preferred_language)."""
    from notifications.models import Notification

    tit, msg = localized_pairs_for_recipient(title_fr, message_fr, recipient)
    return Notification.objects.create(recipient=recipient, title=tit or '', message=msg, **notification_fields)

