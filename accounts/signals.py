from allauth.socialaccount.signals import social_account_added
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from notifications.models import Notification
from notifications.notification_i18n import create_localized_notification
from pins.storage_media import unlink_field_file

from .models import Profile, UserBlock


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


@receiver(post_save, sender=UserBlock)
def userblock_remove_mutual_follows(sender, instance, created, **kwargs):
    """Un blocage retire les abonnements croisés (M2M following)."""
    if not created:
        return
    blocker_profile = instance.blocker.profile
    blocked_profile = instance.blocked.profile
    blocker_profile.following.remove(blocked_profile)
    blocked_profile.following.remove(blocker_profile)
