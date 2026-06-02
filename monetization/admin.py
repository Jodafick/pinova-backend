from django.contrib import admin

from .models import BoostPackage, PartnerCampaign, PinBoost


@admin.register(PartnerCampaign)
class PartnerCampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'sponsor_name', 'is_active', 'priority', 'impressions', 'clicks', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'sponsor_name')


@admin.register(BoostPackage)
class BoostPackageAdmin(admin.ModelAdmin):
    list_display = ('slug', 'label', 'duration_hours', 'amount', 'currency_iso', 'is_active')


@admin.register(PinBoost)
class PinBoostAdmin(admin.ModelAdmin):
    list_display = ('pin', 'owner', 'package', 'status', 'starts_at', 'ends_at')
    list_filter = ('status',)
