from django.contrib import admin
from .models import Profile, SubscriptionPricing, SubscriptionPayment

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'avatar_color')
    search_fields = ('user__username', 'display_name', 'bio')


@admin.register(SubscriptionPricing)
class SubscriptionPricingAdmin(admin.ModelAdmin):
    list_display = ('plan', 'billing_cycle', 'amount', 'currency_iso', 'duration_days', 'is_active')
    list_filter = ('plan', 'billing_cycle', 'currency_iso', 'is_active')
    search_fields = ('plan', 'billing_cycle', 'currency_iso')


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'billing_cycle', 'amount', 'currency_iso', 'status', 'fedapay_transaction_id', 'created_at')
    list_filter = ('plan', 'billing_cycle', 'status', 'currency_iso')
    search_fields = ('user__username', 'fedapay_transaction_id', 'fedapay_reference')
