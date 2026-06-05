from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class PartnerCampaign(models.Model):
    """Publicité partenaire affichée dans les fils (carte native type pin)."""

    title = models.CharField(max_length=120)
    body = models.CharField(max_length=400, blank=True, default='')
    sponsor_name = models.CharField(max_length=80, blank=True, default='')
    image = models.ImageField(upload_to='partner_ads/', blank=True, null=True)
    cta_label = models.CharField(max_length=40, default='En savoir plus')
    cta_url = models.URLField(max_length=500)
    topic_slug = models.CharField(
        max_length=80,
        blank=True,
        default='',
        help_text='Optionnel : cibler un topic (slug ou nom). Vide = tous les sujets.',
    )
    country_code = models.CharField(max_length=2, blank=True, default='')
    priority = models.PositiveSmallIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='partner_campaigns_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-priority', '-created_at']

    def __str__(self):
        return self.title

    def is_live(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class BoostPackage(models.Model):
    """Catalogue des durées de boost pin."""

    slug = models.SlugField(max_length=24, unique=True)
    label = models.CharField(max_length=80)
    duration_hours = models.PositiveIntegerField()
    amount = models.PositiveIntegerField(help_text='Montant en unités mineures (ex. centimes XOF).')
    currency_iso = models.CharField(max_length=10, default='XOF')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['duration_hours']

    def __str__(self):
        return f'{self.slug} ({self.duration_hours}h)'


class PinBoost(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    pin = models.ForeignKey('pins.Pin', on_delete=models.CASCADE, related_name='boosts')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pin_boosts')
    package = models.ForeignKey(BoostPackage, on_delete=models.PROTECT, related_name='boosts')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    fedapay_transaction_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'boost:{self.pin_id}:{self.status}'

    @property
    def is_live(self) -> bool:
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.ends_at and timezone.now() > self.ends_at:
            return False
        return True


class PinPromoCampaign(models.Model):
    """Campagne publicitaire créée par un utilisateur pour promouvoir son pin."""

    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pin_promo_campaigns')
    pin = models.ForeignKey('pins.Pin', on_delete=models.CASCADE, related_name='promo_campaigns')
    package = models.ForeignKey(BoostPackage, on_delete=models.PROTECT, related_name='pin_promo_campaigns')
    headline = models.CharField(max_length=120, blank=True, default='')
    body = models.CharField(max_length=400, blank=True, default='')
    topic_slug = models.CharField(max_length=80, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    fedapay_transaction_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    pin_views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'promo:{self.pin_id}:{self.status}'

    def is_live(self) -> bool:
        if self.status != self.STATUS_ACTIVE:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class TipPlatformConfig(models.Model):
    """Singleton — commission et limites pourboires internes."""

    commission_percent = models.PositiveSmallIntegerField(
        default=10,
        help_text='Part prélevée par Pinova sur chaque pourboire (ex. 10 = 10 %).',
    )
    min_tip_amount = models.PositiveIntegerField(default=500)
    max_tip_amount = models.PositiveIntegerField(default=500_000)
    min_withdrawal_amount = models.PositiveIntegerField(default=5000)
    currency_iso = models.CharField(max_length=10, default='XOF')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tip platform config'

    def __str__(self):
        return f'Tip config ({self.commission_percent} %)'

    @classmethod
    def load(cls) -> 'TipPlatformConfig':
        row, _ = cls.objects.get_or_create(pk=1)
        return row


class CreatorWallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='creator_wallet')
    balance_available = models.PositiveIntegerField(default=0)
    balance_reserved = models.PositiveIntegerField(default=0)
    currency_iso = models.CharField(max_length=10, default='XOF')
    total_received_gross = models.PositiveBigIntegerField(default=0)
    total_received_net = models.PositiveBigIntegerField(default=0)
    total_withdrawn = models.PositiveBigIntegerField(default=0)
    payout_phone = models.CharField(max_length=32, blank=True, default='')
    payout_label = models.CharField(max_length=80, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Creator wallet'

    def __str__(self):
        return f'wallet:{self.user_id}:{self.balance_available}'


class TipTransaction(models.Model):
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

    donor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tips_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tips_received')
    pin = models.ForeignKey('pins.Pin', null=True, blank=True, on_delete=models.SET_NULL, related_name='tips')
    amount_gross = models.PositiveIntegerField()
    commission_amount = models.PositiveIntegerField()
    amount_net = models.PositiveIntegerField()
    currency_iso = models.CharField(max_length=10, default='XOF')
    message = models.CharField(max_length=280, blank=True, default='')
    fedapay_transaction_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    fedapay_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'tip:{self.id}:{self.status}'


class TipWithdrawal(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PAID = 'paid'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PAID, 'Paid'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tip_withdrawals')
    amount = models.PositiveIntegerField()
    currency_iso = models.CharField(max_length=10, default='XOF')
    payout_phone = models.CharField(max_length=32)
    payout_label = models.CharField(max_length=80, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_note = models.CharField(max_length=400, blank=True, default='')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'withdraw:{self.user_id}:{self.amount}:{self.status}'
