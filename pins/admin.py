from django.contrib import admin
from .models import Pin, Save, Like, Comment

@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at', 'likes_count', 'saves_count')
    list_filter = ('author', 'created_at')
    search_fields = ('title', 'description')

@admin.register(Save)
class SaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'created_at')
    list_filter = ('user', 'pin')

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'created_at')
    list_filter = ('user', 'pin')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'text', 'created_at')
    list_filter = ('user', 'pin', 'created_at')
    search_fields = ('text',)
