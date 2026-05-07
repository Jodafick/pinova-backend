from django.contrib import admin
from .models import ExpoPushToken, Notification, PushSubscription

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('message', 'title', 'recipient__username', 'sender__username', 'pin_slug')
    raw_id_fields = ('recipient', 'sender')


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_active', 'updated_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'endpoint')
    raw_id_fields = ('user',)


@admin.register(ExpoPushToken)
class ExpoPushTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'is_active', 'updated_at', 'created_at')
    list_filter = ('is_active', 'platform')
    search_fields = ('user__username', 'token')
    raw_id_fields = ('user',)
