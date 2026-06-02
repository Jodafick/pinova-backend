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
