from django.contrib import admin
from .models import Pin, Save, Like, Comment, Board

@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_private', 'pin_count', 'created_at')
    list_filter = ('user', 'is_private', 'created_at')
    search_fields = ('name', 'description')

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
