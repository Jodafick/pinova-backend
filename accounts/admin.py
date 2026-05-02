from django.contrib import admin
from django import forms
from .models import Profile, SubscriptionPricing, SubscriptionPayment
from .currency_utils import currency_choices_with_symbols


class ProfileAdminForm(forms.ModelForm):
    preferred_currency = forms.ChoiceField(choices=currency_choices_with_symbols())

    class Meta:
        model = Profile
        fields = '__all__'


class SubscriptionPricingAdminForm(forms.ModelForm):
    currency_iso = forms.ChoiceField(choices=currency_choices_with_symbols())

    class Meta:
        model = SubscriptionPricing
        fields = '__all__'

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    form = ProfileAdminForm
    list_display = ('user', 'display_name', 'preferred_currency', 'country_code', 'avatar_color')
    list_filter = ('preferred_currency', 'country_code', 'subscription_plan')
    search_fields = ('user__username', 'display_name', 'bio', 'country_code', 'preferred_currency')


@admin.register(SubscriptionPricing)
class SubscriptionPricingAdmin(admin.ModelAdmin):
    form = SubscriptionPricingAdminForm
    list_display = ('plan', 'billing_cycle', 'amount', 'currency_iso', 'duration_days', 'is_active')
    list_filter = ('plan', 'billing_cycle', 'currency_iso', 'is_active')
    search_fields = ('plan', 'billing_cycle', 'currency_iso')


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'billing_cycle', 'amount', 'currency_iso', 'status', 'fedapay_transaction_id', 'created_at')
    list_filter = ('plan', 'billing_cycle', 'status', 'currency_iso')
    search_fields = ('user__username', 'fedapay_transaction_id', 'fedapay_reference')
