import random
import string
from django.utils import timezone
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    PLAN_FREE = 'free'
    PLAN_PLUS = 'plus'
    PLAN_PRO = 'pro'
    PLAN_CHOICES = [
        (PLAN_FREE, 'Free'),
        (PLAN_PLUS, 'Plus'),
        (PLAN_PRO, 'Pro'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=255, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    avatar_color = models.CharField(max_length=50, default='bg-blue-500')
    following = models.ManyToManyField('self', symmetrical=False, related_name='followers', blank=True)
    subscription_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_FREE)
    subscription_renewal_at = models.DateTimeField(null=True, blank=True)
    translation_quota_monthly = models.PositiveIntegerField(default=5)
    translation_used_monthly = models.PositiveIntegerField(default=0)
    discoverable_profile = models.BooleanField(default=True)
    allow_ai_translation = models.BooleanField(default=True)
    preferred_language = models.CharField(max_length=10, default='fr')
    ad_ads_enabled = models.BooleanField(default=True)
    partner_ads_enabled = models.BooleanField(default=True)
    tips_enabled = models.BooleanField(default=False)
    tips_url = models.URLField(blank=True, null=True)

    @property
    def can_use_private_tags(self):
        return self.subscription_plan in {self.PLAN_PLUS, self.PLAN_PRO}

    @property
    def can_use_comment_gifs(self):
        return self.subscription_plan in {self.PLAN_PLUS, self.PLAN_PRO}

    @property
    def can_download(self):
        return self.subscription_plan in {self.PLAN_PLUS, self.PLAN_PRO}

    @property
    def can_download_4k(self):
        return self.subscription_plan == self.PLAN_PRO

    @property
    def board_limits(self):
        if self.subscription_plan == self.PLAN_PRO:
            return {'private_max': None, 'public_max': None}
        if self.subscription_plan == self.PLAN_PLUS:
            return {'private_max': 10, 'public_max': None}
        return {'private_max': 3, 'public_max': 10}

    def __str__(self):
        return f"{self.user.username}'s profile"

class EmailOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='email_otp')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def generate_otp(self):
        self.otp_code = ''.join(random.choices(string.digits, k=6))
        self.expires_at = timezone.now() + timedelta(minutes=10)
        self.save()

    def __str__(self):
        return f"OTP for {self.user.email}: {self.otp_code}"


class SubscriptionPayment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_FAILED = 'failed'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    BILLING_MONTHLY = 'monthly'
    BILLING_YEARLY = 'yearly'
    BILLING_CHOICES = [
        (BILLING_MONTHLY, 'Monthly'),
        (BILLING_YEARLY, 'Yearly'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_payments')
    plan = models.CharField(max_length=20, choices=Profile.PLAN_CHOICES)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CHOICES, default=BILLING_MONTHLY)
    amount = models.PositiveIntegerField()
    currency_iso = models.CharField(max_length=10, default='XOF')
    fedapay_transaction_id = models.CharField(max_length=64, unique=True)
    fedapay_reference = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    checkout_url = models.URLField(blank=True)
    fedapay_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}:{self.plan}:{self.status}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
