from django.db import models
from django.contrib.auth.models import User

class Notification(models.Model):
    TYPES = (
        ('like', 'Like'),
        ('save', 'Save'),
        ('follow', 'Follow'),
        ('comment', 'Comment'),
        ('welcome', 'Welcome'),
        ('payment', 'Payment'),
        ('plan_change', 'Plan Change'),
        ('system', 'System'),
        ('digest', 'Digest'),
        ('board_invite', 'Board invite'),
        ('scheduled_publish', 'Scheduled pin published'),
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)
    notification_type = models.CharField(max_length=20, choices=TYPES)
    title = models.CharField(max_length=120, blank=True, default='')
    message = models.CharField(max_length=255)
    action_url = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    pin_id = models.IntegerField(null=True, blank=True)
    pin_slug = models.SlugField(max_length=255, null=True, blank=True)
    comment_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        sender_name = self.sender.username if self.sender else 'SYSTEM'
        return f"{sender_name} {self.notification_type} for {self.recipient.username}"


class PushSubscription(models.Model):
    """Abonnement Web Push (Navigateur/PWA — clés VAPID + endpoint FCM/Google pour le web)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"PushSubscription({self.user.username})"


class ExpoPushToken(models.Model):
    """
    Jeton Expo Push (applications React Native via expo-notifications).
    Distinct de PushSubscription : l’API Expo envoie vers FCM/APNs pour le mobile.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expo_push_tokens')
    token = models.CharField(max_length=400, unique=True, db_index=True)
    platform = models.CharField(max_length=24, blank=True, default='')
    user_agent = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"ExpoPushToken({self.user.username})"
