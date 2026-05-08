from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ContestSettings(models.Model):
    DISTRIBUTION_FIXED = 'fixed'
    DISTRIBUTION_CUSTOM = 'custom'
    DISTRIBUTION_PERCENTAGE = 'percentage'
    DISTRIBUTION_CHOICES = [
        (DISTRIBUTION_FIXED, 'Fixed'),
        (DISTRIBUTION_CUSTOM, 'Custom'),
        (DISTRIBUTION_PERCENTAGE, 'Percentage'),
    ]

    contest_key = models.CharField(max_length=7, unique=True, db_index=True, help_text='Format YYYY-MM')
    is_active = models.BooleanField(default=False, db_index=True)
    is_locked = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, default='UTC')
    auto_reset_enabled = models.BooleanField(default=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)

    max_winners = models.PositiveSmallIntegerField(default=3)
    leaderboard_display_pins = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text='Pins shown on the live leaderboard (one row per creator, best pin). Caps the public pins API.',
    )
    distribution_mode = models.CharField(
        max_length=20,
        choices=DISTRIBUTION_CHOICES,
        default=DISTRIBUTION_PERCENTAGE,
    )
    total_prize_pool = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    winner_1_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    winner_2_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    winner_3_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    distribution_weights_json = models.JSONField(default=list, blank=True)

    weight_likes = models.FloatField(default=1.0)
    weight_views = models.FloatField(default=0.15)
    weight_shares = models.FloatField(default=3.0)
    weight_saves = models.FloatField(default=2.0)
    weight_comments = models.FloatField(default=2.5)
    recency_decay_enabled = models.BooleanField(default=True)
    decay_rate = models.FloatField(default=0.02)
    virality_multiplier = models.FloatField(default=1.0)
    share_boost_factor = models.FloatField(default=1.0)
    max_actions_per_user_weight = models.PositiveIntegerField(default=20)

    min_view_duration_seconds = models.PositiveIntegerField(default=2)
    valid_view_time_threshold = models.PositiveIntegerField(default=2)
    max_likes_per_user_per_pin = models.PositiveIntegerField(default=1)
    comment_min_length = models.PositiveIntegerField(default=2)
    trust_score_threshold = models.FloatField(default=0.4)

    notify_top_100 = models.BooleanField(default=True)
    notify_top_10 = models.BooleanField(default=True)
    notify_winner = models.BooleanField(default=True)
    notify_leaderboard_rank_changes = models.BooleanField(
        default=True,
        help_text='Notify creators when their displayed contest rank (best pin) changes; uses anti-spam throttling.',
    )
    notify_rank_change_threshold = models.PositiveIntegerField(default=5)

    leaderboard_refresh_interval = models.PositiveIntegerField(default=3, help_text='seconds')
    websocket_broadcast_threshold = models.FloatField(default=0.2)

    test_mode_enabled = models.BooleanField(default=False)
    simulate_random_engagement = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contest_settings_created',
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-contest_key']

    def __str__(self):
        return f'Contest {self.contest_key}'

    def clean(self):
        if self.start_at >= self.end_at:
            raise ValidationError('start_at must be before end_at.')
        if self.distribution_mode == self.DISTRIBUTION_PERCENTAGE:
            weights = self.distribution_weights_json or []
            if weights and abs(sum(float(v) for v in weights) - 100.0) > 0.01:
                raise ValidationError('distribution_weights_json must sum to 100 for percentage mode.')
        if self.max_winners <= 0:
            raise ValidationError('max_winners must be greater than 0.')


class ContestInteractionEvent(models.Model):
    TYPE_LIKE = 'like'
    TYPE_VIEW = 'view'
    TYPE_SAVE = 'save'
    TYPE_SHARE = 'share'
    TYPE_COMMENT = 'comment'
    TYPE_CHOICES = [
        (TYPE_LIKE, 'Like'),
        (TYPE_VIEW, 'View'),
        (TYPE_SAVE, 'Save'),
        (TYPE_SHARE, 'Share'),
        (TYPE_COMMENT, 'Comment'),
    ]

    contest = models.ForeignKey(ContestSettings, on_delete=models.CASCADE, related_name='events')
    pin = models.ForeignKey('pins.Pin', on_delete=models.CASCADE, related_name='contest_events')
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contest_events')
    interaction_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    dwell_seconds = models.PositiveIntegerField(default=0)
    trust_score = models.FloatField(default=1.0)
    metadata = models.JSONField(default=dict, blank=True)
    is_valid = models.BooleanField(default=True, db_index=True)
    invalid_reason = models.CharField(max_length=120, blank=True, default='')
    score_delta = models.FloatField(default=0.0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contest', 'interaction_type', '-created_at']),
            models.Index(fields=['contest', 'pin', '-created_at']),
            models.Index(fields=['contest', 'actor', '-created_at']),
        ]


class PinContestScore(models.Model):
    contest = models.ForeignKey(ContestSettings, on_delete=models.CASCADE, related_name='pin_scores')
    pin = models.ForeignKey('pins.Pin', on_delete=models.CASCADE, related_name='contest_scores')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contest_pin_scores')
    raw_score = models.FloatField(default=0.0)
    adjusted_score = models.FloatField(default=0.0, db_index=True)
    rank = models.PositiveIntegerField(default=0, db_index=True)
    previous_rank = models.PositiveIntegerField(default=0)
    total_likes = models.PositiveIntegerField(default=0)
    total_views = models.PositiveIntegerField(default=0)
    total_saves = models.PositiveIntegerField(default=0)
    total_shares = models.PositiveIntegerField(default=0)
    total_comments = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('contest', 'pin')]
        ordering = ['rank', '-adjusted_score']


class CreatorContestScore(models.Model):
    contest = models.ForeignKey(ContestSettings, on_delete=models.CASCADE, related_name='creator_scores')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contest_creator_scores')
    adjusted_score = models.FloatField(default=0.0, db_index=True)
    rank = models.PositiveIntegerField(default=0, db_index=True)
    previous_rank = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('contest', 'creator')]
        ordering = ['rank', '-adjusted_score']


class LeaderboardEvent(models.Model):
    contest = models.ForeignKey(ContestSettings, on_delete=models.CASCADE, related_name='leaderboard_events')
    sequence = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=32, db_index=True)
    entity_type = models.CharField(max_length=16, db_index=True)  # pin or creator
    entity_id = models.PositiveIntegerField(db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['sequence']


class LeaderboardSnapshot(models.Model):
    TYPE_PIN = 'pin'
    TYPE_CREATOR = 'creator'
    SNAPSHOT_TYPE_CHOICES = [
        (TYPE_PIN, 'Pin'),
        (TYPE_CREATOR, 'Creator'),
    ]
    contest = models.ForeignKey(ContestSettings, on_delete=models.CASCADE, related_name='snapshots')
    snapshot_type = models.CharField(max_length=12, choices=SNAPSHOT_TYPE_CHOICES)
    rank = models.PositiveIntegerField()
    entity_id = models.PositiveIntegerField()
    score = models.FloatField(default=0.0)
    captured_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-captured_at', 'rank']
        indexes = [
            models.Index(fields=['contest', 'snapshot_type', '-captured_at']),
        ]


class ContestResult(models.Model):
    contest = models.OneToOneField(ContestSettings, on_delete=models.CASCADE, related_name='result')
    winners_json = models.JSONField(default=list, blank=True)
    payout_json = models.JSONField(default=list, blank=True)
    finalized_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-finalized_at']
