from django.contrib import admin, messages
from asgiref.sync import async_to_sync
from googletrans import Translator
from .models import (
    Pin,
    PinVariant,
    PinBoard,
    Save,
    Like,
    Comment,
    CommentLike,
    ContentReport,
    Board,
    Hashtag,
    PrivatePinTag,
    PinProvenanceEvent,
    Topic,
    TopicTranslation,
    LegalDocument,
    BoardCollaborationInvite,
    PinViewEvent,
    SearchInteraction,
)


class PinVariantInline(admin.TabularInline):
    model = PinVariant
    extra = 0


@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'author',
        'topic',
        'visibility',
        'is_story',
        'story_ephemeral',
        'story_expires_at',
        'created_at',
        'likes_count',
        'saves_count',
    )
    list_filter = ('visibility', 'is_story', 'story_ephemeral', 'created_at', 'topic')
    search_fields = ('title', 'description', 'slug', 'topic__name', 'author__username')
    raw_id_fields = ('author', 'topic')
    inlines = [PinVariantInline]


@admin.register(PinVariant)
class PinVariantAdmin(admin.ModelAdmin):
    list_display = ('pin', 'kind', 'created_at')
    search_fields = ('pin__title', 'pin__slug')


@admin.register(PinBoard)
class PinBoardAdmin(admin.ModelAdmin):
    list_display = ('pin', 'board', 'position', 'id')
    list_filter = ('board',)
    search_fields = ('pin__title', 'pin__slug', 'board__name')
    raw_id_fields = ('pin', 'board')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'color', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug')


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_private', 'pins_total_display', 'created_at')

    @admin.display(description='Pins')
    def pins_total_display(self, obj):
        return obj.pins.count()

    list_filter = ('is_private', 'created_at')
    search_fields = ('name', 'description', 'user__username')
    raw_id_fields = ('user',)


@admin.register(Save)
class SaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'pin')


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'pin')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'pin', 'parent', 'text_preview', 'created_at')
    list_filter = ('created_at', 'moderation_hidden', 'hidden_by_owner')
    search_fields = ('text', 'user__username')
    raw_id_fields = ('user', 'pin', 'parent')

    @admin.display(description='Text')
    def text_preview(self, obj):
        t = (obj.text or '')[:80]
        return t + ('…' if len(obj.text or '') > 80 else '')


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'comment')


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'category', 'pin', 'comment', 'reported_user', 'created_at')
    list_filter = ('created_at', 'category')
    search_fields = ('reason', 'details', 'reporter__username', 'reported_user__username')
    raw_id_fields = ('reporter', 'pin', 'comment', 'reported_user')


@admin.register(Hashtag)
class HashtagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(PrivatePinTag)
class PrivatePinTagAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'tag', 'created_at')
    list_filter = ('user', 'created_at')
    search_fields = ('tag',)
    raw_id_fields = ('user', 'pin')


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title_fr', 'contact_email', 'updated_at')
    list_filter = ('slug',)
    search_fields = ('title_fr', 'title_en', 'body_fr', 'body_en', 'contact_email')
    readonly_fields = ('updated_at',)
    actions = ('action_translate_en_from_fr',)

    fieldsets = (
        (None, {'fields': ('slug',)}),
        ('Français', {'fields': ('title_fr', 'body_fr')}),
        ('English', {'fields': ('title_en', 'body_en')}),
        (
            'Contact',
            {
                'fields': ('contact_email',),
                'description': 'Adresse utilisée pour le lien mailto de la page « contact » uniquement.',
            },
        ),
        (
            'Traductions automatiques',
            {
                'fields': ('translations_cache',),
                'classes': ('collapse',),
                'description': 'Cache googletrans pour es, de, it, pt, ar, ja, zh (rempli à la lecture publique ou via l’action ci-dessous).',
            },
        ),
        (None, {'fields': ('updated_at',)}),
    )

    @admin.action(description='Remplir EN depuis FR (googletrans)')
    def action_translate_en_from_fr(self, request, queryset):
        translator = Translator()
        from .legal_page_i18n import translate_long_text_sync
        from .translation import translate_text_to

        n = 0
        for doc in queryset:
            t_fr = (doc.title_fr or '').strip()
            b_fr = (doc.body_fr or '').strip()
            if not t_fr or not b_fr:
                self.message_user(
                    request,
                    f'« {doc.slug} » : titre_fr et corps_fr requis pour traduire.',
                    level=messages.WARNING,
                )
                continue
            try:
                doc.title_en = async_to_sync(translate_text_to)(translator, t_fr, 'en', 'fr')
                doc.body_en = translate_long_text_sync(b_fr, 'en')
                doc.save(update_fields=['title_en', 'body_en'])
                n += 1
            except Exception as exc:
                self.message_user(request, f'« {doc.slug} » : {exc}', level=messages.ERROR)
        if n:
            self.message_user(request, f'{n} page(s) mise(s) à jour (EN).', level=messages.SUCCESS)


@admin.register(BoardCollaborationInvite)
class BoardCollaborationInviteAdmin(admin.ModelAdmin):
    list_display = ('id', 'board', 'invitee', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    raw_id_fields = ('board', 'invitee', 'invited_by')


@admin.register(PinProvenanceEvent)
class PinProvenanceEventAdmin(admin.ModelAdmin):
    list_display = ('pin', 'actor', 'action', 'current_hash', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('current_hash', 'previous_hash', 'pin__slug')
    raw_id_fields = ('pin', 'actor')


@admin.register(TopicTranslation)
class TopicTranslationAdmin(admin.ModelAdmin):
    list_display = ('topic', 'updated_at')
    search_fields = ('topic',)


@admin.register(PinViewEvent)
class PinViewEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'created_at')
    list_filter = ('created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('user', 'pin')


@admin.register(SearchInteraction)
class SearchInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'query', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('query', 'user__username')
    raw_id_fields = ('user',)
