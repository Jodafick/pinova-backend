from django.contrib import admin
from .models import (
    Pin,
    PinVariant,
    Save,
    Like,
    Comment,
    Board,
    Hashtag,
    PrivatePinTag,
    PinProvenanceEvent,
    Topic,
    LegalDocument,
    BoardCollaborationInvite,
)


class PinVariantInline(admin.TabularInline):
    model = PinVariant
    extra = 0


@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'topic', 'visibility', 'is_story', 'created_at', 'likes_count', 'saves_count')
    list_filter = ('author', 'topic', 'visibility', 'created_at')
    search_fields = ('title', 'description', 'topic__name')
    inlines = [PinVariantInline]


@admin.register(PinVariant)
class PinVariantAdmin(admin.ModelAdmin):
    list_display = ('pin', 'kind', 'created_at')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'color', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'icon', 'color')


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_private', 'pins_total_display', 'created_at')

    @admin.display(description='Pins')
    def pins_total_display(self, obj):
        return obj.pins.count()
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


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'updated_at')


@admin.register(BoardCollaborationInvite)
class BoardCollaborationInviteAdmin(admin.ModelAdmin):
    list_display = ('id', 'board', 'invitee', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(PinProvenanceEvent)
class PinProvenanceEventAdmin(admin.ModelAdmin):
    list_display = ('pin', 'actor', 'action', 'current_hash', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('current_hash', 'previous_hash')
