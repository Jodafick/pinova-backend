from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from django import forms
from .models import (
    Profile,
    PinovaSubscriptionConfig,
    SubscriptionPricing,
    SubscriptionPayment,
    SupportTicket,
    EmailOTP,
    SubscriptionSeatInvitation,
    SubscriptionSeatMember,
)
from .currency_utils import currency_choices_with_symbols

User = get_user_model()


@admin.register(User)
class UserAdmin(AuthUserAdmin):
    pass


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
    list_display = ('user', 'display_name', 'preferred_currency', 'country_code', 'subscription_plan')
    list_filter = ('preferred_currency', 'country_code', 'subscription_plan')
    search_fields = ('user__username', 'display_name', 'bio', 'country_code', 'preferred_currency')
    raw_id_fields = ('user', 'subscription_sponsor')


@admin.register(SubscriptionPricing)
class SubscriptionPricingAdmin(admin.ModelAdmin):
    form = SubscriptionPricingAdminForm
    list_display = ('plan', 'billing_cycle', 'seat_bundle', 'amount', 'currency_iso', 'duration_days', 'is_active')
    list_filter = ('plan', 'billing_cycle', 'seat_bundle', 'currency_iso', 'is_active')
    search_fields = ('plan', 'billing_cycle', 'currency_iso')


@admin.register(PinovaSubscriptionConfig)
class PinovaSubscriptionConfigAdmin(admin.ModelAdmin):
    fields = ('annual_discount_percent', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not PinovaSubscriptionConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'billing_cycle', 'amount', 'currency_iso', 'status', 'fedapay_transaction_id', 'created_at')
    list_filter = ('plan', 'billing_cycle', 'status', 'currency_iso')
    search_fields = ('user__username', 'fedapay_transaction_id', 'fedapay_reference')
    raw_id_fields = ('user',)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('user__username', 'subject', 'message')
    raw_id_fields = ('user',)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)


@admin.register(SubscriptionSeatInvitation)
class SubscriptionSeatInvitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'invitee', 'status', 'expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('owner__username', 'invitee__username')
    raw_id_fields = ('owner', 'invitee')
    readonly_fields = ('id', 'token_hash', 'created_at')


@admin.register(SubscriptionSeatMember)
class SubscriptionSeatMemberAdmin(admin.ModelAdmin):
    list_display = ('owner', 'member', 'joined_at')
    search_fields = ('owner__username', 'member__username')
    raw_id_fields = ('owner', 'member')
