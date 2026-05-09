from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserReferralCode(models.Model):
    """Code referral immuable par utilisateur."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='referral_code_row',
    )
    code = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id}:{self.code}'


class ReferralPendingIntent(models.Model):
    """
    Intent pré-inscription : session Django (web) ou device_binding_id (mobile / deep link).
    """

    session_key = models.CharField(max_length=128, blank=True, default='', db_index=True)
    device_binding_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    code_normalized = models.CharField(max_length=32, db_index=True)
    utm_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['session_key', '-created_at']),
            models.Index(fields=['device_binding_id', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(session_key='') | ~models.Q(device_binding_id=''),
                name='referral_intent_session_or_device',
            ),
        ]

    def __str__(self):
        return f'intent {self.code_normalized}'


class ReferralAttribution(models.Model):
    STATUS_PENDING_EMAIL = 'pending_email'
    STATUS_ACTIVE = 'active'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [
        (STATUS_PENDING_EMAIL, 'Pending email verification'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_REVOKED, 'Revoked'),
    ]

    SOURCE_LINK_QUERY = 'link_query'
    SOURCE_DEEP_LINK = 'deep_link'
    SOURCE_SIGNUP_FIELD = 'signup_field'
    SOURCE_INTENT_API = 'intent_api'
    SOURCE_OAUTH_COMPLETION = 'oauth_completion'
    SOURCE_ONBOARDING_MODAL = 'onboarding_modal'
    SOURCE_CHOICES = [
        (SOURCE_LINK_QUERY, 'Link query'),
        (SOURCE_DEEP_LINK, 'Deep link'),
        (SOURCE_SIGNUP_FIELD, 'Signup field'),
        (SOURCE_INTENT_API, 'Intent API'),
        (SOURCE_OAUTH_COMPLETION, 'OAuth completion'),
        (SOURCE_ONBOARDING_MODAL, 'Onboarding modal'),
    ]

    referee = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='referral_attribution',
    )
    referrer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='referrals_given',
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING_EMAIL, db_index=True)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_SIGNUP_FIELD)
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    rewards_granted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    signup_ip = models.CharField(max_length=64, blank=True, default='', db_index=True)
    signup_device_hash = models.CharField(max_length=128, blank=True, default='', db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['referrer', 'status']),
            models.Index(fields=['rewards_granted_at']),
        ]

    def __str__(self):
        return f'{self.referee_id} <- {self.referrer_id} ({self.status})'


class ReferralEvent(models.Model):
    """Journal d’événements referral (brut + validé via is_valid / score_delta)."""

    TYPE_LINK_OPENED = 'link_opened'
    TYPE_SIGNUP_STARTED = 'signup_started'
    TYPE_SIGNUP_VALIDATED = 'signup_validated'
    TYPE_FIRST_LOGIN = 'first_login'
    TYPE_FIRST_POST = 'first_post'
    TYPE_ENGAGEMENT = 'engagement'
    TYPE_RETENTION = 'retention'
    TYPE_REFERRAL_FINALIZED = 'referral_finalized'
    TYPE_REWARD_DEFERRED = 'reward_deferred'
    TYPE_REWARD_GRANTED = 'reward_granted'
    TYPE_FRAUD_BLOCKED = 'fraud_blocked'
    TYPE_CHOICES = [
        (TYPE_LINK_OPENED, 'Link opened'),
        (TYPE_SIGNUP_STARTED, 'Signup started'),
        (TYPE_SIGNUP_VALIDATED, 'Signup validated'),
        (TYPE_FIRST_LOGIN, 'First login'),
        (TYPE_FIRST_POST, 'First post'),
        (TYPE_ENGAGEMENT, 'Engagement'),
        (TYPE_RETENTION, 'Retention'),
        (TYPE_REFERRAL_FINALIZED, 'Referral finalized'),
        (TYPE_REWARD_DEFERRED, 'Reward deferred'),
        (TYPE_REWARD_GRANTED, 'Reward granted'),
        (TYPE_FRAUD_BLOCKED, 'Fraud blocked'),
    ]

    contest = models.ForeignKey(
        'contests.ContestSettings',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referral_events',
    )
    event_type = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)
    referee = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='referral_events_as_referee',
    )
    referrer = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='referral_events_as_referrer',
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_valid = models.BooleanField(default=True, db_index=True)
    invalid_reason = models.CharField(max_length=120, blank=True, default='')
    score_delta = models.FloatField(default=0.0)
    trust_score = models.FloatField(default=1.0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contest', 'event_type', '-created_at']),
            models.Index(fields=['referrer', '-created_at']),
        ]


class ReferrerReferralScore(models.Model):
    """Score agrégé par parrain et période concours (contest_key mensuel)."""

    contest = models.ForeignKey(
        'contests.ContestSettings',
        on_delete=models.CASCADE,
        related_name='referrer_referral_scores',
    )
    referrer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='referrer_referral_scores',
    )
    total_score = models.FloatField(default=0.0, db_index=True)
    rank = models.PositiveIntegerField(default=0, db_index=True)
    previous_rank = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('contest', 'referrer')]
        ordering = ['rank', '-total_score']


class ReferralLeaderboardEvent(models.Model):
    """Flux temps réel (WebSocket) pour le leaderboard referral, calqué sur contests.LeaderboardEvent."""

    contest = models.ForeignKey(
        'contests.ContestSettings',
        on_delete=models.CASCADE,
        related_name='referral_leaderboard_events',
    )
    sequence = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=32, db_index=True)
    entity_id = models.PositiveIntegerField(db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['sequence']


class ReferralSignupContext(models.Model):
    """Contexte device/IP à l’inscription (détection vélocité / audit)."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='referral_signup_context',
    )
    signup_ip = models.CharField(max_length=64, blank=True, default='', db_index=True)
    device_hash = models.CharField(max_length=128, blank=True, default='', db_index=True)
    user_agent_snippet = models.CharField(max_length=256, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['signup_ip', '-created_at']),
            models.Index(fields=['device_hash', '-created_at']),
        ]


class UserReferralTrust(models.Model):
    """Trust score dynamique (0–1) pour pondération / éligibilité referral."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referral_trust_profile')
    score = models.FloatField(default=0.5, db_index=True)
    signals_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'trust {self.user_id}={self.score:.2f}'


class ReferralAuditLog(models.Model):
    """Piste d’audit sécurité parrainage."""

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='referral_audit_logs')
    attribution = models.ForeignKey(
        'ReferralAttribution',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=64, db_index=True)
    ip = models.CharField(max_length=64, blank=True, default='')
    device_hash = models.CharField(max_length=128, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']


class ReferralSuspicionFlag(models.Model):
    """File de revue : anomalies / blocage manuel."""

    STATUS_OPEN = 'open'
    STATUS_RESOLVED = 'resolved'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_DISMISSED, 'Dismissed'),
    ]

    attribution = models.ForeignKey(
        'ReferralAttribution',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='suspicion_flags',
    )
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='referral_suspicion_flags')
    code = models.CharField(max_length=64, db_index=True)
    severity = models.PositiveSmallIntegerField(default=1, help_text='1=info, 5=critique')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]


class ReferralContestResult(models.Model):
    """Archivage du concours referral mensuel (miroir logique de contests.ContestResult)."""

    contest = models.OneToOneField(
        'contests.ContestSettings',
        on_delete=models.CASCADE,
        related_name='referral_result',
    )
    winners_json = models.JSONField(default=list, blank=True)
    leaderboard_snapshot_json = models.JSONField(default=list, blank=True)
    stats_json = models.JSONField(default=dict, blank=True)
    finalized_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-finalized_at']

    def __str__(self):
        return f'referral-result {self.contest_id}'
