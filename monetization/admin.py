from django.contrib import admin

from .models import (
    BoostPackage,
    CreatorWallet,
    PartnerCampaign,
    PinBoost,
    TipPlatformConfig,
    TipTransaction,
    TipWithdrawal,
)
from .tip_services import mark_withdrawal_paid, reject_withdrawal


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


@admin.register(TipPlatformConfig)
class TipPlatformConfigAdmin(admin.ModelAdmin):
    list_display = ('commission_percent', 'min_tip_amount', 'max_tip_amount', 'min_withdrawal_amount', 'currency_iso')


@admin.register(CreatorWallet)
class CreatorWalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance_available', 'balance_reserved', 'total_received_net', 'payout_phone')
    search_fields = ('user__username',)


@admin.register(TipTransaction)
class TipTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'donor', 'recipient', 'amount_gross', 'commission_amount', 'amount_net', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('donor__username', 'recipient__username', 'fedapay_transaction_id')


@admin.register(TipWithdrawal)
class TipWithdrawalAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'payout_phone', 'created_at', 'processed_at')
    list_filter = ('status',)
    actions = ['mark_paid', 'mark_rejected']

    @admin.action(description='Marquer comme payé (virement effectué)')
    def mark_paid(self, request, queryset):
        for row in queryset.filter(status=TipWithdrawal.STATUS_PENDING):
            mark_withdrawal_paid(row)

    @admin.action(description='Rejeter et recréditer le solde')
    def mark_rejected(self, request, queryset):
        for row in queryset.filter(status=TipWithdrawal.STATUS_PENDING):
            reject_withdrawal(row, admin_note='Rejeté via admin')
