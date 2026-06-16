from django.contrib import admin
from django import forms

from accounts.currency_utils import currency_choices_with_symbols

from .models import (
    BoostPackage,
    CreatorWallet,
    PartnerCampaign,
    FotoBoost,
    FotoPromoCampaign,
    TipPlatformConfig,
    TipTransaction,
    TipWithdrawal,
)
from .tip_services import mark_withdrawal_paid, reject_withdrawal


class BoostPackageAdminForm(forms.ModelForm):
    currency_iso = forms.ChoiceField(choices=currency_choices_with_symbols())

    class Meta:
        model = BoostPackage
        fields = '__all__'


@admin.register(PartnerCampaign)
class PartnerCampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'sponsor_name', 'is_active', 'priority', 'impressions', 'clicks', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'sponsor_name')


@admin.register(BoostPackage)
class BoostPackageAdmin(admin.ModelAdmin):
    """Tarifs boost foto et campagnes pub — même principe que SubscriptionPricing (backoffice)."""
    form = BoostPackageAdminForm
    list_display = ('slug', 'label', 'package_kind', 'duration_hours', 'amount', 'currency_iso', 'is_active', 'updated_at')
    list_filter = ('package_kind', 'is_active', 'currency_iso')
    search_fields = ('slug', 'label')
    ordering = ('package_kind', 'duration_hours')
    fieldsets = (
        (None, {
            'fields': ('slug', 'label', 'package_kind', 'duration_hours', 'amount', 'currency_iso', 'is_active'),
        }),
        ('Audit', {
            'fields': ('updated_at',),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('updated_at',)


@admin.register(FotoPromoCampaign)
class FotoPromoCampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'headline', 'package', 'status', 'impressions', 'clicks', 'created_at')
    list_filter = ('status',)
    search_fields = ('owner__username', 'headline', 'fedapay_transaction_id')
    raw_id_fields = ('owner', 'pin', 'package')


@admin.register(FotoBoost)
class FotoBoostAdmin(admin.ModelAdmin):
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
