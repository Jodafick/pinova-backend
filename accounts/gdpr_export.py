"""Export RGPD — collecte JSON + archive ZIP."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from notifications.models import Notification
from fotos.models import Comment, Foto
from monetization.models import TipTransaction, TipWithdrawal


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _profile_payload(user: User) -> dict[str, Any]:
    profile = user.profile
    return {
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'date_joined': _iso(user.date_joined),
        'display_name': profile.display_name,
        'bio': profile.bio,
        'preferred_language': profile.preferred_language,
        'preferred_currency': profile.preferred_currency,
        'country_code': profile.country_code,
        'birth_date': profile.birth_date.isoformat() if profile.birth_date else None,
        'private_profile': profile.private_profile,
        'discoverable_profile': profile.discoverable_profile,
        'subscription_plan': profile.subscription_plan,
        'subscription_renewal_at': _iso(profile.subscription_renewal_at),
        'onboarding_completed_at': _iso(profile.onboarding_completed_at),
        'account_scheduled_deletion_at': _iso(profile.account_scheduled_deletion_at),
    }


def _pins_payload(user: User) -> list[dict[str, Any]]:
    rows = Foto.objects.filter(author=user).select_related('topic').order_by('-created_at')
    out: list[dict[str, Any]] = []
    for foto in rows:
        out.append(
            {
                'id': foto.id,
                'slug': foto.slug,
                'title': foto.title,
                'description': foto.description,
                'topic': foto.topic_name if hasattr(pin, 'topic_name') else (pin.topic.name if foto.topic_id else None),
                'visibility': foto.visibility,
                'is_story': foto.is_story,
                'created_at': _iso(pin.created_at),
                'updated_at': _iso(getattr(pin, 'updated_at', None)),
                'public_tags': list(pin.hashtags.values_list('name', flat=True)),
                'link': foto.link,
            },
        )
    return out


def _comments_payload(user: User) -> list[dict[str, Any]]:
    rows = Comment.objects.filter(user=user).select_related('pin').order_by('-created_at')
    return [
        {
            'id': row.id,
            'foto_slug': row.pin.slug if row.foto_id else None,
            'text': row.text,
            'gif_url': row.gif_url,
            'parent_id': row.parent_id,
            'created_at': _iso(row.created_at),
            'updated_at': _iso(row.updated_at),
        }
        for row in rows
    ]


def _notifications_payload(user: User) -> list[dict[str, Any]]:
    rows = Notification.objects.filter(recipient=user).order_by('-created_at')[:5000]
    return [
        {
            'id': row.id,
            'type': row.notification_type,
            'title': row.title,
            'message': row.message,
            'action_url': row.action_url,
            'metadata': row.metadata,
            'foto_slug': row.foto_slug,
            'is_read': row.is_read,
            'created_at': _iso(row.created_at),
        }
        for row in rows
    ]


def _subscriptions_payload(user: User) -> dict[str, Any]:
    from accounts.models import SubscriptionPayment

    profile = user.profile
    payments = SubscriptionPayment.objects.filter(user=user).order_by('-created_at')[:100]
    return {
        'plan': profile.subscription_plan,
        'renewal_at': _iso(profile.subscription_renewal_at),
        'cancel_at_period_end': profile.subscription_cancel_at_period_end,
        'scheduled_plan': profile.subscription_scheduled_plan or None,
        'payments': [
            {
                'id': row.id,
                'plan': row.plan,
                'billing_cycle': row.billing_cycle,
                'amount_minor': row.amount,
                'currency_iso': row.currency_iso,
                'status': row.status,
                'created_at': _iso(row.created_at),
                'fedapay_transaction_id': row.fedapay_transaction_id,
            }
            for row in payments
        ],
    }


def _tips_payload(user: User) -> dict[str, Any]:
    sent = TipTransaction.objects.filter(donor=user).order_by('-created_at')[:500]
    received = TipTransaction.objects.filter(recipient=user).order_by('-created_at')[:500]
    withdrawals = TipWithdrawal.objects.filter(user=user).order_by('-created_at')[:200]
    return {
        'sent': [
            {
                'id': row.id,
                'recipient_id': row.recipient_id,
                'amount_gross': row.amount_gross,
                'amount_net': row.amount_net,
                'currency_iso': row.currency_iso,
                'status': row.status,
                'message': row.message,
                'created_at': _iso(row.created_at),
            }
            for row in sent
        ],
        'received': [
            {
                'id': row.id,
                'donor_id': row.donor_id,
                'amount_gross': row.amount_gross,
                'amount_net': row.amount_net,
                'currency_iso': row.currency_iso,
                'status': row.status,
                'message': row.message,
                'created_at': _iso(row.created_at),
            }
            for row in received
        ],
        'withdrawals': [
            {
                'id': row.id,
                'amount': row.amount,
                'currency_iso': row.currency_iso,
                'status': row.status,
                'created_at': _iso(row.created_at),
            }
            for row in withdrawals
        ],
    }


def build_user_export_bundle(user: User) -> dict[str, Any]:
    return {
        'exported_at': timezone.now().isoformat(),
        'format_version': 1,
        'profile': _profile_payload(user),
        'fotos': _pins_payload(user),
        'comments': _comments_payload(user),
        'notifications': _notifications_payload(user),
        'subscriptions': _subscriptions_payload(user),
        'tips': _tips_payload(user),
    }


def build_export_zip_bytes(user: User) -> bytes:
    bundle = build_user_export_bundle(user)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            'fotoce-export.json',
            json.dumps(bundle, ensure_ascii=False, indent=2, default=str),
        )
        for key in ('profile', 'fotos', 'comments', 'notifications', 'subscriptions', 'tips'):
            zf.writestr(
                f'{key}.json',
                json.dumps(bundle[key], ensure_ascii=False, indent=2, default=str),
            )
    return buffer.getvalue()


def export_storage_dir() -> Path:
    base = Path(getattr(settings, 'MEDIA_ROOT', 'media')) / 'gdpr_exports'
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_export_zip(user: User, job_id: int) -> str:
    """Persiste le ZIP et retourne le chemin relatif sous MEDIA_ROOT."""
    data = build_export_zip_bytes(user)
    rel = Path('gdpr_exports') / str(user.id) / f'export_{job_id}.zip'
    full = Path(settings.MEDIA_ROOT) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    return str(rel).replace('\\', '/')
