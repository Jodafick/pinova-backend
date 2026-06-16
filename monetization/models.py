from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class PartnerCampaign(models.Model):
    """Publicité partenaire affichée dans les fils (carte native type foto)."""

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
    targeting = models.JSONField(default=dict, blank=True)
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
    """Catalogue tarifaire boost foto et campagnes pub (paramétrable via admin Django)."""

    KIND_BOOST = 'boost'
    KIND_CAMPAIGN = 'campaign'
    KIND_BOTH = 'both'
    KIND_CHOICES = [
        (KIND_BOOST, 'Boost foto'),
        (KIND_CAMPAIGN, 'Campagne pub'),
        (KIND_BOTH, 'Boost et campagne'),
    ]

    slug = models.SlugField(max_length=24, unique=True)
    label = models.CharField(max_length=80)
    package_kind = models.CharField(
        max_length=16,
        choices=KIND_CHOICES,
        default=KIND_BOTH,
        db_index=True,
        help_text='Restreint l’usage du pack (boost, campagne pub, ou les deux).',
    )
    duration_hours = models.PositiveIntegerField()
    amount = models.PositiveIntegerField(help_text='Montant en unités mineures (ex. centimes XOF).')
    currency_iso = models.CharField(max_length=10, default='XOF')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['package_kind', 'duration_hours']

    def __str__(self):
        return f'{self.slug} ({self.duration_hours}h · {self.package_kind})'

    def allows_boost(self) -> bool:
        return self.package_kind in {self.KIND_BOOST, self.KIND_BOTH}

    def allows_campaign(self) -> bool:
        return self.package_kind in {self.KIND_CAMPAIGN, self.KIND_BOTH}


class FotoBoost(models.Model):
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

    foto = models.ForeignKey('fotos.Foto', on_delete=models.CASCADE, related_name='boosts')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='foto_boosts')
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
        return f'boost:{self.foto_id}:{self.status}'

    @property
    def is_live(self) -> bool:
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.ends_at and timezone.now() > self.ends_at:
            return False
        return True


class FotoPromoCampaign(models.Model):
    """Campagne publicitaire créée par un utilisateur (contenu autonome, sans foto obligatoire)."""

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

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='foto_promo_campaigns')
    foto = models.ForeignKey(
        'fotos.Foto',
        on_delete=models.CASCADE,
        related_name='promo_campaigns',
        null=True,
        blank=True,
    )
    package = models.ForeignKey(BoostPackage, on_delete=models.PROTECT, related_name='foto_promo_campaigns')
    headline = models.CharField(max_length=120, blank=True, default='')
    body = models.CharField(max_length=400, blank=True, default='')
    image = models.ImageField(upload_to='creator_ads/', blank=True, null=True)
    media = models.FileField(
        upload_to='creator_ads/media/',
        blank=True,
        null=True,
        storage='monetization.storage.creator_ad_media_storage',
    )
    MEDIA_IMAGE = 'image'
    MEDIA_VIDEO = 'video'
    MEDIA_TYPE_CHOICES = [
        (MEDIA_IMAGE, 'Image'),
        (MEDIA_VIDEO, 'Video'),
    ]
    media_type = models.CharField(max_length=8, choices=MEDIA_TYPE_CHOICES, default=MEDIA_IMAGE)
    cta_label = models.CharField(max_length=40, default='En savoir plus', blank=True)
    cta_url = models.URLField(max_length=500, blank=True, default='')
    topic_slug = models.CharField(max_length=80, blank=True, default='')
    targeting = models.JSONField(default=dict, blank=True)
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
        label = self.headline or (f'pin:{self.foto_id}' if self.foto_id else 'standalone')
        return f'promo:{label}:{self.status}'

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
        help_text='Part prélevée par Fotoce sur chaque pourboire (ex. 10 = 10 %).',
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
    foto = models.ForeignKey('fotos.Foto', null=True, blank=True, on_delete=models.SET_NULL, related_name='tips')
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


class WebhookEventProcessed(models.Model):
    """Idempotence — un couple (transaction_id, event_type) ne déclenche l'activation qu'une fois."""

    transaction_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-processed_at']
        constraints = [
            models.UniqueConstraint(
                fields=['transaction_id', 'event_type'],
                name='monetization_webhook_event_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['transaction_id', 'event_type'], name='monetization_tx_evt_idx'),
        ]

    def __str__(self):
        return f'{self.transaction_id}:{self.event_type}'
