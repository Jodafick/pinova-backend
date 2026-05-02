from django.contrib import admin
from .models import Notification, PushSubscription

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('message', 'recipient__username', 'sender__username')


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_active', 'updated_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'endpoint')
