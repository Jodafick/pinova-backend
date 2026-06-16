"""
Textes canoniques français pour les notifications, puis traduction (googletrans)
vers la langue préférée du destinataire — même stratégie que fotos.topic_i18n.

À l’écriture : `create_localized_notification` enregistre dans `metadata['i18n']` les chaînes
FR + `display_lang` (langue utilisée pour `title` / `message` en base).

À la lecture : le serializer peut recalculer titre/message si la langue du profil a changé,
sans nouveau couple FR (évite notifications figées après changement de langue).
"""

from __future__ import annotations

from django.contrib.auth.models import User
from googletrans import Translator
from asgiref.sync import async_to_sync

from fotos.translation import translate_text_to
from fotos.topic_i18n import SUPPORTED_TOPIC_LANGS


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
    """Notification avec title/message pour `recipient_language`; FR canonique conservé dans metadata."""
    from notifications.delivery import enrich_notification_metadata
    from notifications.models import Notification

    md = notification_fields.pop('metadata', None) or {}
    if not isinstance(md, dict):
        md = {}
    ntype = str(notification_fields.get('notification_type') or '')
    md = enrich_notification_metadata(md, notification_type=ntype)

    tit_fr_raw = (title_fr or '')[:NOTIFICATION_TITLE_MAX]
    msg_fr_raw = (message_fr or '')[:NOTIFICATION_MESSAGE_MAX]
    lang0 = recipient_language(recipient)
    tit, msg = localize_notification_strings(tit_fr_raw, msg_fr_raw, lang0)

    prev_i18n = md.get('i18n')
    if not isinstance(prev_i18n, dict):
        prev_i18n = {}
    md['i18n'] = {
        **prev_i18n,
        'title_fr': tit_fr_raw,
        'message_fr': msg_fr_raw,
        'display_lang': lang0,
    }

    return Notification.objects.create(
        recipient=recipient,
        title=tit or '',
        message=msg,
        metadata=md,
        **notification_fields,
    )

