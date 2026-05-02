from django.contrib import admin
from .models import Pin, Save, Like, Comment, Board, Hashtag, PrivatePinTag, PinProvenanceEvent, Topic

@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'topic', 'visibility', 'created_at', 'likes_count', 'saves_count')
    list_filter = ('author', 'topic', 'visibility', 'created_at')
    search_fields = ('title', 'description', 'topic__name')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'color', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'icon', 'color')


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_private', 'pin_count', 'created_at')
    list_filter = ('user', 'is_private')
    search_fields = ('name', 'description')

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
    list_display = ('user', 'pin', 'parent', 'text', 'created_at')
    list_filter = ('user', 'pin', 'created_at')
    search_fields = ('text',)


@admin.register(Hashtag)
class HashtagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(PrivatePinTag)
class PrivatePinTagAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'tag', 'created_at')
    list_filter = ('user',)
    search_fields = ('tag',)


@admin.register(PinProvenanceEvent)
class PinProvenanceEventAdmin(admin.ModelAdmin):
    list_display = ('pin', 'actor', 'action', 'current_hash', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('current_hash', 'previous_hash')
