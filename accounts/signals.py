from allauth.socialaccount.signals import social_account_added
from django.dispatch import receiver

from notifications.models import Notification


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

    Notification.objects.create(
        recipient=user,
        sender=None,
        notification_type='welcome',
        title='Bienvenue sur PINOVA',
        message=f"Compte créé avec {provider_label}. Bienvenue {user.username} !",
        action_url='/',
        metadata={
            'stage': 'social_signup',
            'provider': provider,
        },
    )
