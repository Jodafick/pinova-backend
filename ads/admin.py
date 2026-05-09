from django.contrib import admin

from ads import models as m


@admin.register(m.Advertiser)
class AdvertiserAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'contact_email', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'legal_name', 'contact_email')


@admin.register(m.BusinessAccount)
class BusinessAccountAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'advertiser', 'owner', 'is_active')
    list_filter = ('is_active',)


@admin.register(m.Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'business_account', 'status', 'objective', 'bid_strategy', 'start_at', 'end_at')
    list_filter = ('status', 'objective')


@admin.register(m.CampaignBudget)
class CampaignBudgetAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'budget_type', 'budget_micro', 'spend_micro', 'pacing')


@admin.register(m.AdCategory)
class AdCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(m.AudienceSegment)
class AudienceSegmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'business_account', 'updated_at')


@admin.register(m.AdCreative)
class AdCreativeAdmin(admin.ModelAdmin):
    list_display = ('headline', 'business_account', 'brand_name', 'created_at')


class AdTargetingInline(admin.StackedInline):
    model = m.AdTargeting
    extra = 0


@admin.register(m.Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ('name', 'campaign', 'ad_format', 'status', 'created_at')
    list_filter = ('status', 'ad_format')
    inlines = [AdTargetingInline]


@admin.register(m.AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = ('id', 'ad', 'user', 'placement', 'served_at', 'is_valid')
    list_filter = ('placement', 'is_valid')


@admin.register(m.AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = ('id', 'ad', 'user', 'clicked_at', 'is_suspicious')


@admin.register(m.AdView)
class AdViewAdmin(admin.ModelAdmin):
    list_display = ('id', 'ad', 'user', 'started_at', 'duration_ms', 'completed')


@admin.register(m.AdWatchSession)
class AdWatchSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'ad', 'user', 'started_at', 'total_watched_ms')


@admin.register(m.AdReport)
class AdReportAdmin(admin.ModelAdmin):
    list_display = ('ad', 'user', 'reason', 'created_at')


@admin.register(m.AdHide)
class AdHideAdmin(admin.ModelAdmin):
    list_display = ('ad', 'user', 'created_at')


@admin.register(m.AdFrequencyTracking)
class AdFrequencyTrackingAdmin(admin.ModelAdmin):
    list_display = ('user', 'ad', 'impressions_24h', 'last_shown_at')


@admin.register(m.UserInterestScore)
class UserInterestScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'key_type', 'key_slug', 'score', 'last_signal_at')


@admin.register(m.UserBehaviorProfile)
class UserBehaviorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_watch_seconds_7d', 'last_active_at')


@admin.register(m.UserTrustScore)
class UserTrustScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'trust', 'updated_at')


@admin.register(m.AdQualityScore)
class AdQualityScoreAdmin(admin.ModelAdmin):
    list_display = ('ad', 'quality_0_100', 'hide_rate', 'report_rate', 'updated_at')


@admin.register(m.AdDeliveryLog)
class AdDeliveryLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'placement', 'chosen_ad', 'created_at')


@admin.register(m.AdPerformanceSnapshot)
class AdPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('ad', 'granularity', 'period_start', 'impressions', 'ctr', 'engagement_rate')


@admin.register(m.AdPendingEvent)
class AdPendingEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'created_at', 'processed_at', 'attempts')
