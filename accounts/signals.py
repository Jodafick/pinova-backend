from allauth.socialaccount.signals import social_account_added
from django.db.models.signals import post_delete
from django.dispatch import receiver

from notifications.models import Notification
from notifications.notification_i18n import create_localized_notification
from pins.storage_media import unlink_field_file

from .models import Profile


@receiver(social_account_added)
def notify_social_signup(sender, request, sociallogin, **kwargs):
    user = getattr(sociallogin, 'user', None)
    if not user or not user.pk:
        return

    provider = str(getattr(sociallogin.account, 'provider', '') or 'social').strip().lower()
    provider_label = provider.capitalize() if provider else 'Social'

    # Avoid duplicate welcome-social notification when linking multiple accounts.
    if Notification.objects.filter(
        recipient=user,
        notification_type='welcome',
        metadata__stage='social_signup',
        metadata__provider=provider,
    ).exists():
        return

    create_localized_notification(
        recipient=user,
        sender=None,
        notification_type='welcome',
        title_fr='Bienvenue sur PINOVA',
        message_fr=f"Compte créé avec {provider_label}. Bienvenue {user.username} !",
        action_url='/',
        metadata={
            'stage': 'social_signup',
            'provider': provider,
        },
    )


@receiver(post_delete, sender=Profile)
def purge_profile_avatar_file(sender, instance, **kwargs):
    unlink_field_file(instance.avatar)
