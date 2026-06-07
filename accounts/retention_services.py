"""Campagnes rétention — push streak, emails J+7 / J+30."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone

from notifications.notification_i18n import create_localized_notification
from pins.models import Pin

from .discovery_streak import is_streak_at_risk
from .models import Profile

logger = logging.getLogger(__name__)


def _user_lang(profile: Profile) -> str:
    return (profile.preferred_language or 'fr').lower().split('-')[0]


def count_following_new_pins(user: User, *, days: int = 7) -> int:
    """Pins publiés par les créateurs suivis sur la période."""
    profile = getattr(user, 'profile', None)
    if not profile:
        return 0
    following_ids = list(profile.following.values_list('user_id', flat=True))
    if not following_ids:
        return 0
    since = timezone.now() - timedelta(days=days)
    return Pin.objects.filter(author_id__in=following_ids, created_at__gte=since).count()


def reset_retention_email_flags(profile: Profile) -> None:
    """Réinitialise les flags email après reconnexion (nouveau cycle d'inactivité)."""
    profile.retention_j7_email_sent_at = None
    profile.retention_j30_email_sent_at = None
    profile.save(update_fields=['retention_j7_email_sent_at', 'retention_j30_email_sent_at'])


def send_streak_reminder_for_profile(profile: Profile) -> bool:
    """Push + notif in-app si streak discovery à risque (J+1)."""
    if not profile.notifications_streak_reminders:
        return False
    if not is_streak_at_risk(profile):
        return False
    today = timezone.localdate()
    if profile.discovery_streak_reminder_sent_date == today:
        return False

    user = profile.user
    count = int(profile.discovery_streak_count or 0)
    create_localized_notification(
        recipient=user,
        sender=None,
        notification_type='streak_reminder',
        title_fr='Ton streak découverte est en jeu 🔥',
        message_fr=f'Visite l’onglet Explorer pour garder ton streak de {count} jour(s).',
        action_url='/',
        metadata={'kind': 'discovery_streak_reminder', 'streak_count': count, 'delivery_mode': 'ws_and_push', 'in_app_toast': True},
    )
    profile.discovery_streak_reminder_sent_date = today
    profile.save(update_fields=['discovery_streak_reminder_sent_date'])
    return True


def run_discovery_streak_reminders(*, limit: int = 5000) -> dict:
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    profiles = list(
        Profile.objects.filter(
            discovery_streak_count__gte=1,
            discovery_streak_last_date=yesterday,
            notifications_streak_reminders=True,
        )
        .exclude(discovery_streak_reminder_sent_date=today)
        .select_related('user')[:limit]
    )
    sent = 0
    for profile in profiles:
        try:
            if send_streak_reminder_for_profile(profile):
                sent += 1
        except Exception:
            logger.exception('streak_reminder_fail user_id=%s', profile.user_id)
    return {'sent': sent, 'scanned': len(profiles)}


def _inactive_users_window(*, days: int, limit: int):
    now = timezone.now()
    start = now - timedelta(days=days + 1)
    end = now - timedelta(days=days)
    return (
        User.objects.filter(
            is_active=True,
            last_login__gte=start,
            last_login__lt=end,
            profile__notifications_reactivation_emails=True,
        )
        .select_related('profile')
        .order_by('id')[:limit]
    )


def send_j7_reactivation_email(user: User) -> bool:
    profile = user.profile
    if profile.retention_j7_email_sent_at:
        return False
    email = (user.email or '').strip()
    if not email:
        return False

    pin_count = count_following_new_pins(user, days=7)
    if pin_count <= 0:
        return False

    lang = _user_lang(profile)
    base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/') or 'http://localhost:5174'
    explore_url = f'{base}/'

    if lang.startswith('fr'):
        subject = 'Pinova — tes créateurs ont publié de nouveaux pins'
        body = (
            f'Bonjour {profile.display_name or user.username},\n\n'
            f'Les créateurs que tu suis ont publié {pin_count} nouveau(x) pin(s) cette semaine.\n'
            f'Reviens découvrir : {explore_url}\n\n'
            f'— L’équipe Pinova'
        )
    else:
        subject = 'Pinova — creators you follow posted new pins'
        body = (
            f'Hi {profile.display_name or user.username},\n\n'
            f'Creators you follow posted {pin_count} new pin(s) this week.\n'
            f'Come back to explore: {explore_url}\n\n'
            f'— The Pinova team'
        )

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@pinova.app'
    send_mail(subject, body, from_email, [email], fail_silently=False)
    profile.retention_j7_email_sent_at = timezone.now()
    profile.save(update_fields=['retention_j7_email_sent_at'])
    return True


def send_j30_monthly_email(user: User) -> bool:
    profile = user.profile
    if profile.retention_j30_email_sent_at:
        return False
    email = (user.email or '').strip()
    if not email:
        return False

    pin_count = count_following_new_pins(user, days=30)
    lang = _user_lang(profile)
    base = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/') or 'http://localhost:5174'
    contest_url = f'{base}/contest/live'
    referral_url = f'{base}/referrals/invite'

    if lang.startswith('fr'):
        subject = 'Pinova — ton mois en résumé'
        body = (
            f'Bonjour {profile.display_name or user.username},\n\n'
            f'Ce mois-ci, tes créateurs ont publié {pin_count} pin(s).\n\n'
            f'Participe au concours en cours : {contest_url}\n'
            f'Invite des amis et gagne des récompenses : {referral_url}\n\n'
            f'On a hâte de te revoir sur Pinova !\n\n'
            f'— L’équipe Pinova'
        )
    else:
        subject = 'Pinova — your monthly recap'
        body = (
            f'Hi {profile.display_name or user.username},\n\n'
            f'This month, creators you follow posted {pin_count} pin(s).\n\n'
            f'Join the live contest: {contest_url}\n'
            f'Invite friends and earn rewards: {referral_url}\n\n'
            f'We hope to see you back on Pinova!\n\n'
            f'— The Pinova team'
        )

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@pinova.app'
    send_mail(subject, body, from_email, [email], fail_silently=False)
    profile.retention_j30_email_sent_at = timezone.now()
    profile.save(update_fields=['retention_j30_email_sent_at'])
    return True


def run_j7_reactivation_emails(*, limit: int = 2000) -> dict:
    sent = 0
    skipped = 0
    for user in _inactive_users_window(days=7, limit=limit):
        if user.profile.retention_j7_email_sent_at:
            skipped += 1
            continue
        try:
            if send_j7_reactivation_email(user):
                sent += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
            logger.exception('j7_reactivation_fail user_id=%s', user.id)
    return {'sent': sent, 'skipped': skipped}


def run_j30_reactivation_emails(*, limit: int = 2000) -> dict:
    sent = 0
    skipped = 0
    for user in _inactive_users_window(days=30, limit=limit):
        if user.profile.retention_j30_email_sent_at:
            skipped += 1
            continue
        try:
            if send_j30_monthly_email(user):
                sent += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
            logger.exception('j30_reactivation_fail user_id=%s', user.id)
    return {'sent': sent, 'skipped': skipped}
