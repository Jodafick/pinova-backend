from django.contrib import admin

from .models import (
    ReferralAttribution,
    ReferralAuditLog,
    ReferralContestResult,
    ReferralContestSettings,
    ReferralEvent,
    ReferralLeaderboardEvent,
    ReferralPendingIntent,
    ReferralSignupContext,
    ReferralSuspicionFlag,
    ReferrerReferralScore,
    UserReferralCode,
    UserReferralTrust,
)


@admin.register(UserReferralCode)
class UserReferralCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'created_at')
    search_fields = ('code', 'user__username', 'user__email')
    readonly_fields = ('code', 'created_at')


@admin.register(ReferralPendingIntent)
class ReferralPendingIntentAdmin(admin.ModelAdmin):
    list_display = ('code_normalized', 'session_key', 'device_binding_id', 'expires_at', 'created_at')
    list_filter = ('created_at',)


@admin.register(ReferralAttribution)
class ReferralAttributionAdmin(admin.ModelAdmin):
    list_display = ('referee', 'referrer', 'status', 'source', 'email_verified_at', 'rewards_granted_at', 'created_at')
    list_filter = ('status', 'source')
    raw_id_fields = ('referee', 'referrer')


@admin.register(ReferralEvent)
class ReferralEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'referee', 'referrer', 'is_valid', 'score_delta', 'created_at')
    list_filter = ('event_type', 'is_valid')
    raw_id_fields = ('referee', 'referrer', 'contest')


@admin.register(ReferrerReferralScore)
class ReferrerReferralScoreAdmin(admin.ModelAdmin):
    list_display = ('contest', 'referrer', 'total_score', 'rank', 'updated_at')
    raw_id_fields = ('referrer',)


@admin.register(ReferralLeaderboardEvent)
class ReferralLeaderboardEventAdmin(admin.ModelAdmin):
    list_display = ('sequence', 'contest', 'event_type', 'entity_id', 'created_at')
    list_filter = ('event_type',)


@admin.register(ReferralSignupContext)
class ReferralSignupContextAdmin(admin.ModelAdmin):
    list_display = ('user', 'signup_ip', 'device_hash', 'created_at')
    search_fields = ('signup_ip', 'device_hash', 'user__username')


@admin.register(UserReferralTrust)
class UserReferralTrustAdmin(admin.ModelAdmin):
    list_display = ('user', 'score', 'updated_at')
    search_fields = ('user__username',)


@admin.register(ReferralAuditLog)
class ReferralAuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'attribution', 'ip', 'created_at')
    list_filter = ('action',)
    search_fields = ('action', 'ip', 'device_hash')
    raw_id_fields = ('user', 'attribution')


@admin.register(ReferralSuspicionFlag)
class ReferralSuspicionFlagAdmin(admin.ModelAdmin):
    list_display = ('code', 'severity', 'status', 'user', 'attribution', 'created_at')
    list_filter = ('status', 'code', 'severity')
    search_fields = ('notes', 'code')
    raw_id_fields = ('user', 'attribution')


@admin.register(ReferralContestResult)
class ReferralContestResultAdmin(admin.ModelAdmin):
    list_display = ('contest', 'finalized_at')
    readonly_fields = ('finalized_at',)


@admin.register(ReferralContestSettings)
class ReferralContestSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'contest',
        'defer_rewards',
        'min_days_before_reward',
        'referee_trust_threshold',
        'updated_at',
    )
    raw_id_fields = ('contest',)
