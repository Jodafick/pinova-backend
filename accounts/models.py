import random
import string
import uuid
from django.utils import timezone
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MaxValueValidator, MinValueValidator

from pins.storage_media import unlink_named


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
    preferred_currency = models.CharField(max_length=3, default='XOF')
    country_code = models.CharField(max_length=2, blank=True, default='')
    tips_enabled = models.BooleanField(default=False)
    tips_url = models.URLField(blank=True, null=True)
    private_profile = models.BooleanField(default=False)
    notifications_followers = models.BooleanField(default=True)
    notifications_saves = models.BooleanField(default=True)
    notifications_recommendations = models.BooleanField(default=False)
    # Pro : digest hebdomadaire e-mail / push (« pins les plus vus »).
    notifications_digest_creator_weekly = models.BooleanField(default=True)
    subscription_cancel_at_period_end = models.BooleanField(default=False)
    subscription_scheduled_plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        blank=True,
        default='',
    )
    # Lien de partage pour profil privé (?share=…)
    share_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    # Obligatoire pour publier du média ; utilisée pour distinguer mineurs / adultes (≥18 ans).
    birth_date = models.DateField(null=True, blank=True)
    # Suppression différée : purge serveur après cette date si la demande est maintenue.
    account_scheduled_deletion_at = models.DateTimeField(null=True, blank=True)
    # Une fois défini : l'utilisateur ne peut plus activer l'offre essai Plus 14 j.
    subscription_trial_consumed_at = models.DateTimeField(null=True, blank=True)
    subscription_seat_bundle = models.CharField(max_length=24, blank=True, default='solo')
    subscription_sponsor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='provisioned_subscription_seats',
    )
    # Plus/Pro uniquement en pratique : si False, médias signalés « sensibles » non floutés par défaut pour le spectateur majeur connecté.
    sensitive_media_blur_by_default = models.BooleanField(default=True)
    # Majeur vérifié : masque les pins d’autrui marquées sensibles (flux, tableau, détail renvoie 404).
    hide_sensitive_pins = models.BooleanField(default=False)
    ad_ads_enabled = models.BooleanField(default=True)
    partner_ads_enabled = models.BooleanField(default=True)

    # --- Identité étendue ---
    first_name = models.CharField(max_length=80, blank=True, default='')
    last_name = models.CharField(max_length=80, blank=True, default='')
    cover_image = models.ImageField(upload_to='covers/', null=True, blank=True)
    GENDER_CHOICES = [
        ('', 'Prefer not to say'),
        ('woman', 'Woman'),
        ('man', 'Man'),
        ('non_binary', 'Non-binary'),
        ('other', 'Other'),
    ]
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, default='')
    pronouns = models.CharField(max_length=40, blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    website = models.URLField(blank=True, default='')
    job_title = models.CharField(max_length=120, blank=True, default='')
    school = models.CharField(max_length=200, blank=True, default='')
    company = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=32, blank=True, default='')

    # --- Découverte sociale (slugs JSON) ---
    interests = models.JSONField(default=list, blank=True)
    followed_onboarding_creators = models.JSONField(default=list, blank=True)

    # --- Personnalisation (sync multi-appareils) ---
    THEME_LIGHT = 'light'
    THEME_DARK = 'dark'
    THEME_SYSTEM = 'system'
    THEME_MODE_CHOICES = [
        (THEME_LIGHT, 'Light'),
        (THEME_DARK, 'Dark'),
        (THEME_SYSTEM, 'System'),
    ]
    theme_mode = models.CharField(max_length=10, choices=THEME_MODE_CHOICES, default=THEME_SYSTEM)
    accent_color = models.CharField(max_length=24, default='rose')
    date_format = models.CharField(max_length=24, default='auto')
    timezone = models.CharField(max_length=64, blank=True, default='')

    # --- Présence / confidentialité sociale ---
    PRESENCE_AVAILABLE = 'available'
    PRESENCE_BUSY = 'busy'
    PRESENCE_INVISIBLE = 'invisible'
    PRESENCE_CHOICES = [
        (PRESENCE_AVAILABLE, 'Available'),
        (PRESENCE_BUSY, 'Busy'),
        (PRESENCE_INVISIBLE, 'Invisible'),
    ]
    presence_status = models.CharField(
        max_length=16, choices=PRESENCE_CHOICES, default=PRESENCE_AVAILABLE,
    )
    show_activity = models.BooleanField(default=True)
    show_last_seen = models.BooleanField(default=True)
    allow_dm = models.BooleanField(default=True)
    allow_tags_mentions = models.BooleanField(default=True)

    # --- Profil avancé ---
    favorite_quote = models.CharField(max_length=280, blank=True, default='')
    hobbies = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    social_links = models.JSONField(default=dict, blank=True)

    # --- Onboarding ---
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def can_use_private_tags(self):
        return self.subscription_plan in {self.PLAN_PLUS, self.PLAN_PRO}

    @property
    def can_use_comment_gifs(self):
        """GIF (URL ou fichier) et pièces jointes image dans les commentaires (Plus / Pro)."""
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

    def save(self, *args, **kwargs):
        """Supprime les fichiers média précédents du stockage si remplacés ou retirés."""
        old_avatar_name = ''
        old_avatar_storage = None
        old_cover_name = ''
        old_cover_storage = None
        if self.pk:
            try:
                prev = Profile.objects.only('avatar', 'cover_image').get(pk=self.pk)
                if prev.avatar:
                    old_avatar_name = prev.avatar.name
                    old_avatar_storage = prev.avatar.storage
                if prev.cover_image:
                    old_cover_name = prev.cover_image.name
                    old_cover_storage = prev.cover_image.storage
            except Profile.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        new_avatar = self.avatar.name if self.avatar else ''
        if (
            old_avatar_name
            and old_avatar_name != new_avatar
            and old_avatar_storage is not None
        ):
            unlink_named(old_avatar_storage, old_avatar_name)

        new_cover = self.cover_image.name if self.cover_image else ''
        if (
            old_cover_name
            and old_cover_name != new_cover
            and old_cover_storage is not None
        ):
            unlink_named(old_cover_storage, old_cover_name)

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


class MobileOAuthLoginCode(models.Model):
    """Code court à usage unique pour transférer une session OAuth web vers l'app mobile."""

    code_hash = models.CharField(max_length=64, unique=True, db_index=True)
    device_binding_id = models.CharField(max_length=128, db_index=True)
    mobile_state_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    def is_usable(self):
        return self.consumed_at is None and timezone.now() <= self.expires_at


class SubscriptionPricing(models.Model):
    BILLING_MONTHLY = 'monthly'
    BILLING_YEARLY = 'yearly'
    BILLING_CHOICES = [
        (BILLING_MONTHLY, 'Monthly'),
        (BILLING_YEARLY, 'Yearly'),
    ]
    SEAT_SOLO = 'solo'
    SEAT_FAMILY = 'family'
    SEAT_TEAM = 'team'
    SEAT_CHOICES = [
        (SEAT_SOLO, 'Solo'),
        (SEAT_FAMILY, 'Family'),
        (SEAT_TEAM, 'Team'),
    ]

    plan = models.CharField(max_length=20, choices=Profile.PLAN_CHOICES)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CHOICES, default=BILLING_MONTHLY)
    seat_bundle = models.CharField(max_length=24, choices=SEAT_CHOICES, default=SEAT_SOLO)
    amount = models.PositiveIntegerField()
    duration_days = models.PositiveIntegerField(default=30)
    currency_iso = models.CharField(max_length=10, default='XOF')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('plan', 'billing_cycle', 'seat_bundle')
        ordering = ['plan', 'billing_cycle', 'seat_bundle']

    def __str__(self):
        return f"{self.plan}:{self.billing_cycle}:{self.seat_bundle}:{self.amount} {self.currency_iso}"


class PinovaSubscriptionConfig(models.Model):
    """Singleton (pk fixe à 1) : paramètres d’affichage / marketing pour les abonnements."""

    annual_discount_percent = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text=(
            'Badge −X % « annuel » sur la page Premium et valeur API annual_discount_percent. '
            'Mettre 0 pour masquer le badge ; les paiements suivent encore les lignes SubscriptionPricing.'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuration abonnement Pinova'
        verbose_name_plural = 'Configuration abonnement Pinova'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'annual_discount_percent': 10})
        return obj

    def __str__(self):
        return 'Configuration abonnement Pinova'


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
    invoice_url = models.URLField(blank=True, max_length=500)
    promo_bundle = models.CharField(max_length=24, blank=True, default='')
    fedapay_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}:{self.plan}:{self.status}"


class SupportTicket(models.Model):
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_RESOLVED, 'Resolved'),
    ]
    PRIORITY_NORMAL = 'normal'
    PRIORITY_PRIORITY = 'priority'
    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, 'Normal'),
        (PRIORITY_PRIORITY, 'Priority'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=140)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}:{self.subject[:30]}:{self.status}"


class SubscriptionSeatInvitation(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_EXPIRED = 'expired'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'pending'),
        (STATUS_ACCEPTED, 'accepted'),
        (STATUS_DECLINED, 'declined'),
        (STATUS_EXPIRED, 'expired'),
        (STATUS_REVOKED, 'revoked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seat_invitations_sent')
    invitee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seat_invitations_received')
    token_hash = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['invitee', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'invitee'],
                condition=models.Q(status='pending'),
                name='uniq_pending_seat_invite_owner_invitee',
            ),
        ]

    def __str__(self):
        return f'seat-inv {self.owner_id}->{self.invitee_id} ({self.status})'


class SubscriptionSeatMember(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seat_memberships_owned')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seat_memberships_received')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'member'], name='uniq_subscription_seat_owner_member'),
            models.UniqueConstraint(fields=['member'], name='uniq_subscription_seat_member_singleton'),
        ]
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['member']),
        ]

    def __str__(self):
        return f'seat {self.member_id} @ {self.owner_id}'


class UserBlock(models.Model):
    """Le bloqueur ne voit plus le contenu du bloqué ; le bloqué ne voit plus celui du bloqueur (symétrique côté flux)."""

    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_blocks_made')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_blocks_received')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['blocker', 'blocked'], name='uniq_userblock_blocker_blocked'),
            models.CheckConstraint(condition=~Q(blocker_id=F('blocked_id')), name='userblock_no_self'),
        ]
        indexes = [
            models.Index(fields=['blocker', '-created_at']),
            models.Index(fields=['blocked', '-created_at']),
        ]

    def __str__(self):
        return f'{self.blocker_id} blocked {self.blocked_id}'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
