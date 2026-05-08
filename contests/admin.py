from django.contrib import admin

from .models import (
    ContestInteractionEvent,
    ContestResult,
    ContestSettings,
    CreatorContestScore,
    LeaderboardEvent,
    LeaderboardSnapshot,
    PinContestScore,
)


@admin.register(ContestSettings)
class ContestSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'contest_key',
        'is_active',
        'is_locked',
        'start_at',
        'end_at',
        'max_winners',
        'leaderboard_display_pins',
        'updated_at',
    )
    list_filter = ('is_active', 'is_locked', 'distribution_mode', 'auto_reset_enabled')
    search_fields = ('contest_key',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Contest Window', {'fields': ('contest_key', 'is_active', 'is_locked', 'timezone', 'start_at', 'end_at', 'auto_reset_enabled')}),
        (
            'Rewards',
            {
                'classes': ('collapse',),
                'fields': (
                    'max_winners',
                    'leaderboard_display_pins',
                    'distribution_mode',
                    'total_prize_pool',
                    'winner_1_amount',
                    'winner_2_amount',
                    'winner_3_amount',
                    'distribution_weights_json',
                ),
            },
        ),
        ('Ranking Rules', {'classes': ('collapse',), 'fields': ('weight_likes', 'weight_views', 'weight_shares', 'weight_saves', 'weight_comments', 'recency_decay_enabled', 'decay_rate', 'virality_multiplier', 'share_boost_factor', 'max_actions_per_user_weight')}),
        ('Anti-fraud', {'classes': ('collapse',), 'fields': ('min_view_duration_seconds', 'valid_view_time_threshold', 'max_likes_per_user_per_pin', 'comment_min_length', 'trust_score_threshold')}),
        (
            'Notifications',
            {
                'classes': ('collapse',),
                'fields': (
                    'notify_top_100',
                    'notify_top_10',
                    'notify_winner',
                    'notify_leaderboard_rank_changes',
                    'notify_rank_change_threshold',
                ),
            },
        ),
        ('Realtime', {'classes': ('collapse',), 'fields': ('leaderboard_refresh_interval', 'websocket_broadcast_threshold')}),
        ('Debug / Test', {'classes': ('collapse',), 'fields': ('test_mode_enabled', 'simulate_random_engagement', 'version', 'created_by')}),
        ('Audit', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(ContestInteractionEvent)
class ContestInteractionEventAdmin(admin.ModelAdmin):
    list_display = ('contest', 'interaction_type', 'pin', 'actor', 'is_valid', 'score_delta', 'created_at')
    list_filter = ('contest', 'interaction_type', 'is_valid')
    search_fields = ('pin__title', 'actor__username', 'contest__contest_key')
    raw_id_fields = ('pin', 'actor')


@admin.register(PinContestScore)
class PinContestScoreAdmin(admin.ModelAdmin):
    list_display = ('contest', 'pin', 'creator', 'adjusted_score', 'rank', 'previous_rank', 'updated_at')
    list_filter = ('contest',)
    search_fields = ('pin__title', 'pin__slug', 'creator__username', 'contest__contest_key')
    raw_id_fields = ('pin', 'creator')


@admin.register(CreatorContestScore)
class CreatorContestScoreAdmin(admin.ModelAdmin):
    list_display = ('contest', 'creator', 'adjusted_score', 'rank', 'previous_rank', 'updated_at')
    list_filter = ('contest',)
    search_fields = ('creator__username', 'contest__contest_key')
    raw_id_fields = ('creator',)


@admin.register(LeaderboardEvent)
class LeaderboardEventAdmin(admin.ModelAdmin):
    list_display = ('sequence', 'contest', 'event_type', 'entity_type', 'entity_id', 'created_at')
    list_filter = ('contest', 'event_type', 'entity_type')
    search_fields = ('contest__contest_key',)


@admin.register(LeaderboardSnapshot)
class LeaderboardSnapshotAdmin(admin.ModelAdmin):
    list_display = ('contest', 'snapshot_type', 'rank', 'entity_id', 'score', 'captured_at')
    list_filter = ('contest', 'snapshot_type')
    search_fields = ('contest__contest_key',)


@admin.register(ContestResult)
class ContestResultAdmin(admin.ModelAdmin):
    list_display = ('contest', 'finalized_at')
    search_fields = ('contest__contest_key',)
