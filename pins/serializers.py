from rest_framework import serializers
import re

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Case, When, Value, IntegerField, Exists, OuterRef
from django.utils import timezone
from .models import (
    Pin,
    PinVariant,
    Topic,
    Comment,
    Like,
    Save,
    Board,
    Hashtag,
    PrivatePinTag,
    PinProvenanceEvent,
    PinBoard,
    BoardCollaborationInvite,
    ContentReport,
)

from pinova_backend.media.cache import build_versioned_media_url

from accounts.models import Profile
from accounts.serializers import ProfileSerializer
from .comment_access import viewer_sees_comment_content, user_can_comment_on_pin
from .visibility import profile_is_verified_adult
from accounts.age_policy import profile_can_publish_content
from .moderation import (
    validate_pin_text,
    validate_clean_text_fields,
    apply_pin_creation_rate_limits,
    pin_body_fingerprint,
    enforce_identical_content_flood,
    pin_is_story_flag,
)
from .topic_i18n import resolve_topic_language, ensure_topic_translation, warm_topic_translations_for_new_topic
from .visual_moderation import apply_server_visual_moderation_to_pin
from .api_locale import localize_api_user_message

HASHTAG_RE = re.compile(r'#([A-Za-z0-9_]{2,80})')
MENTION_RE = re.compile(r'@([A-Za-z0-9_\.]{2,80})')


def story_video_min_bytes_required() -> int:
    mb = float(getattr(settings, 'PIN_STORY_VIDEO_MIN_SIZE_MB', 0) or 0)
    if mb <= 0:
        return 0
    return int(round(mb * 1024 * 1024))


def story_video_max_bytes_allowed() -> int:
    mb = float(getattr(settings, 'PIN_STORY_VIDEO_MAX_SIZE_MB', 0) or 0)
    if mb <= 0:
        return 0
    return int(round(mb * 1024 * 1024))


_STORY_VIDEO_BAD_FORMAT_FR = (
    'Format vidéo non reconnu. Formats acceptés : MP4, WebM ou MOV.'
)


def _validate_story_video_max_size(uploaded, request=None) -> None:
    mx = story_video_max_bytes_allowed()
    if mx <= 0:
        return
    sz = int(getattr(uploaded, 'size', 0) or 0)
    if sz > mx:
        mxf = float(getattr(settings, 'PIN_STORY_VIDEO_MAX_SIZE_MB', 128) or 128)
        fr_msg = (
            f'La vidéo dépasse la taille maximale autorisée ({mxf:g} Mo). '
            f'Réduisez la qualité ou raccourcissez la durée avant envoi.'
        )
        raise serializers.ValidationError(localize_api_user_message(fr_msg, request))


def _validate_story_video_min_size(uploaded, request=None) -> None:
    mn = story_video_min_bytes_required()
    if mn <= 0:
        return
    sz = int(getattr(uploaded, 'size', 0) or 0)
    if sz < mn:
        mbf = float(getattr(settings, 'PIN_STORY_VIDEO_MIN_SIZE_MB', 1) or 1)
        fr_msg = (
            f'La vidéo est trop petite (minimum {mbf:g} Mo). '
            f'Veuillez envoyer une version moins compressée ou de meilleure qualité.'
        )
        raise serializers.ValidationError(localize_api_user_message(fr_msg, request))


def _secure_pin_image_upload(value, request):
    if not value:
        return value
    user_id = request.user.id if request and request.user.is_authenticated else None
    from .upload_security import secure_image_upload

    return secure_image_upload(value, kind='pin', request=request, user_id=user_id)


def _secure_story_video_upload(value, request):
    if not value:
        return value
    _validate_story_video_max_size(value, request=request)
    _validate_story_video_min_size(value, request=request)
    user_id = request.user.id if request and request.user.is_authenticated else None
    from .upload_security import secure_video_upload

    return secure_video_upload(value, request=request, user_id=user_id)


def extract_hashtags(text: str) -> list[str]:
    if not text:
        return []
    return sorted({m.lower() for m in HASHTAG_RE.findall(text)})


def extract_mentions(text: str) -> list[str]:
    if not text:
        return []
    return sorted({m.lower() for m in MENTION_RE.findall(text)})


class BoardSerializer(serializers.ModelSerializer):
    pin_count = serializers.SerializerMethodField()
    collaborator_count = serializers.SerializerMethodField()
    preview_images = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Board
        fields = [
            'id',
            'name',
            'description',
            'is_private',
            'created_at',
            'pin_count',
            'collaborator_count',
            'preview_images',
            'is_owner',
            'owner_username',
        ]

    def validate(self, attrs):
        name = attrs.get('name', getattr(self.instance, 'name', '') if self.instance else '')
        description = attrs.get('description', getattr(self.instance, 'description', '') if self.instance else '')
        validate_clean_text_fields(
            {
                'name': str(name or ''),
                'description': str(description or ''),
            },
            message='Ce champ contient un contenu inapproprie. Merci de le modifier.',
        )
        return attrs

    def get_preview_images(self, obj):
        from .visibility import pin_is_visible_for_request

        request = self.context.get('request')
        rows = (
            PinBoard.objects.filter(board=obj)
            .select_related('pin')
            .order_by('position', 'id')[:24]
        )
        urls = []
        for row in rows:
            pin = getattr(row, 'pin', None)
            if not pin or not request or not pin_is_visible_for_request(pin, request):
                continue
            img = getattr(pin, 'image', None)
            if not img:
                continue
            urls.append(build_versioned_media_url(request, img))
            if len(urls) >= 6:
                break
        return urls

    def get_pin_count(self, obj):
        total = getattr(obj, 'pins_total', None)
        if total is not None:
            return total
        return obj.pins.count()

    def get_collaborator_count(self, obj):
        return obj.collaborators.count()

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.user_id == request.user.id


class BoardCollaborationInviteSerializer(serializers.ModelSerializer):
    board_name = serializers.CharField(source='board.name', read_only=True)
    board_id = serializers.IntegerField(source='board.id', read_only=True)
    owner_username = serializers.CharField(source='board.user.username', read_only=True)
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)

    class Meta:
        model = BoardCollaborationInvite
        fields = [
            'id',
            'board_id',
            'board_name',
            'owner_username',
            'invited_by_username',
            'status',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'board_id',
            'board_name',
            'owner_username',
            'invited_by_username',
            'status',
            'created_at',
        ]


class PinProvenanceEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = PinProvenanceEvent
        fields = [
            'id',
            'actor_username',
            'action',
            'previous_hash',
            'current_hash',
            'metadata',
            'created_at',
        ]


class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    display_name = serializers.CharField(source='user.profile.display_name', read_only=True)
    avatar_color = serializers.CharField(source='user.profile.avatar_color', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()
    replies_next_page = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    hashtags = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    viewer_has_reported = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id',
            'user',
            'username',
            'display_name',
            'avatar_color',
            'avatar_url',
            'text',
            'gif_url',
            'media',
            'parent',
            'mentions',
            'hashtags',
            'original_language',
            'translated_text',
            'created_at',
            'updated_at',
            'likes_count',
            'is_liked',
            'viewer_has_reported',
            'hidden_by_owner',
            'moderation_hidden',
            'replies',
            'replies_next_page',
            'replies_count',
        ]
        read_only_fields = ['mentions', 'hashtags', 'translated_text', 'replies', 'hidden_by_owner', 'moderation_hidden']

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        profile = getattr(obj.user, 'profile', None)
        if not profile:
            return ''
        avatar = getattr(profile, 'avatar', None)
        if not avatar or not getattr(avatar, 'name', ''):
            return ''
        if request:
            return build_versioned_media_url(request, avatar)
        return avatar.url

    def to_representation(self, instance):
        request = self.context.get('request')
        pin = instance.pin
        full = viewer_sees_comment_content(instance, pin, request)
        data = super().to_representation(instance)
        if not full:
            data['text'] = ''
            data['gif_url'] = None
            data['media'] = None
            data['translated_text'] = ''
            data['hashtags'] = []
            data['mentions'] = []
            data['content_masked'] = True
        else:
            data['content_masked'] = False
        data['hidden_by_owner'] = instance.hidden_by_owner
        data['moderation_hidden'] = getattr(instance, 'moderation_hidden', False)
        if (
            full
            and request
            and getattr(instance, 'media', None)
            and getattr(instance.media, 'name', None)
            and data.get('media')
        ):
            data['media'] = build_versioned_media_url(request, instance.media)
        return data

    def get_replies(self, obj):
        if not self.context.get('include_replies', True):
            return []
        replies_page_size = int(self.context.get('replies_page_size', 3))
        replies_sort = (self.context.get('replies_sort') or 'recent').lower()
        highlighted_comment_id = self.context.get('highlighted_comment_id')
        replies = obj.replies.all().select_related('user', 'user__profile')
        req = self.context.get('request')
        if req and req.user.is_authenticated:
            replies = replies.annotate(
                _viewer_has_reported_comment=Exists(
                    ContentReport.objects.filter(
                        reporter=req.user,
                        comment_id=OuterRef('pk'),
                    )
                )
            )
        if replies_sort == 'relevant':
            replies = replies.annotate(likes_total=Count('comment_likes')).order_by('-likes_total', '-created_at')
        else:
            replies = replies.order_by('-created_at')
        if highlighted_comment_id:
            replies = replies.annotate(
                highlight_priority=Case(
                    When(id=highlighted_comment_id, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by('highlight_priority', *replies.query.order_by)
        chunk = replies[:replies_page_size]
        nested_context = {**self.context, 'include_replies': False}
        return CommentSerializer(chunk, many=True, context=nested_context).data

    def get_replies_next_page(self, obj):
        if not self.context.get('include_replies', True):
            return None
        replies_page_size = int(self.context.get('replies_page_size', 3))
        total = obj.replies.count()
        return 2 if total > replies_page_size else None

    def get_replies_count(self, obj):
        return obj.replies.count()

    def get_hashtags(self, obj):
        return [f"#{h.name}" for h in obj.hashtags.all()]

    def get_likes_count(self, obj):
        return obj.comment_likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.comment_likes.filter(user=request.user).exists()
        return False

    def get_viewer_has_reported(self, obj):
        v = getattr(obj, '_viewer_has_reported_comment', None)
        if v is not None:
            return bool(v)
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return ContentReport.objects.filter(reporter=request.user, comment=obj).exists()

    def create(self, validated_data):
        comment = super().create(validated_data)
        hashtags = extract_hashtags(comment.text)
        mentions = extract_mentions(comment.text)
        if hashtags:
            hashtag_objs = []
            for tag in hashtags:
                hashtag, _ = Hashtag.objects.get_or_create(name=tag)
                hashtag_objs.append(hashtag)
            comment.hashtags.set(hashtag_objs)
        comment.mentions = mentions
        comment.save(update_fields=['mentions'])
        return comment

class PinSerializer(serializers.ModelSerializer):
    author_profile = ProfileSerializer(source='author.profile', read_only=True)
    topic = serializers.CharField(required=False, allow_blank=True)
    topic_meta = serializers.SerializerMethodField()
    boards = serializers.SerializerMethodField()
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    story_video_url = serializers.SerializerMethodField(read_only=True)
    story_display_image_url = serializers.SerializerMethodField(read_only=True)
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    saves_count = serializers.SerializerMethodField()
    shares_count = serializers.IntegerField(read_only=True)
    can_comment = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    viewer_has_reported = serializers.SerializerMethodField()
    is_boosted = serializers.SerializerMethodField()
    hashtags = serializers.SerializerMethodField()
    private_tags = serializers.SerializerMethodField()
    private_tags_input = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False,
    )
    public_tags_input = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False,
    )
    board_ids_input = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )
    media_sensitive_blur = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Pin
        fields = [
            'id',
            'slug',
            'title',
            'description',
            'link',
            'image',
            'story_display_image_url',
            'story_video',
            'story_video_url',
            'author',
            'author_profile',
            'boards',
            'topic',
            'topic_meta',
            'visibility',
            'hashtags',
            'private_tags',
            'private_tags_input',
            'public_tags_input',
            'board_ids_input',
            'scheduled_publish_at',
            'is_story',
            'story_ephemeral',
            'story_expires_at',
            'created_at',
            'likes_count',
            'comments_count',
            'comments_policy',
            'can_comment',
            'needs_review',
            'saves_count',
            'shares_count',
            'is_liked',
            'is_saved',
            'viewer_has_reported',
            'media_sensitive_blur',
            'is_boosted',
        ]
        read_only_fields = ['story_expires_at', 'needs_review', 'story_ephemeral']
        extra_kwargs = {
            'author': {'required': False},
            'story_video': {'write_only': True},
        }

    def get_story_video_url(self, obj):
        if not getattr(obj, 'story_video', None) or not obj.story_video.name:
            return None
        request = self.context.get('request')
        if request:
            return build_versioned_media_url(request, obj.story_video)
        return obj.story_video.url

    def get_story_display_image_url(self, obj):
        """URL absolue du visuel story : variante 9:16 si présente, sinon image principale."""
        if not getattr(obj, 'is_story', False):
            return None
        request = self.context.get('request')
        if not request:
            return None

        try:
            for pv in obj.variant_assets.all():
                if pv.kind == PinVariant.KIND_STORY and pv.image and getattr(pv.image, 'name', ''):
                    return build_versioned_media_url(request, pv.image)
        except Exception:
            pass
        if obj.image and getattr(obj.image, 'name', ''):
            return build_versioned_media_url(request, obj.image)
        return None

    def get_likes_count(self, obj):
        annotated = getattr(obj, '_feed_likes_count', None)
        if annotated is not None:
            return int(annotated)
        return obj.likes_count

    def get_comments_count(self, obj):
        annotated = getattr(obj, '_feed_comments_count', None)
        if annotated is not None:
            return int(annotated)
        return obj.comments_count

    def get_saves_count(self, obj):
        annotated = getattr(obj, '_feed_saves_count', None)
        if annotated is not None:
            return int(annotated)
        return obj.saves_count

    def validate_image(self, value):
        return _secure_pin_image_upload(value, self.context.get('request'))

    def validate_story_video(self, value):
        return _secure_story_video_upload(value, self.context.get('request'))

    def get_boards(self, obj):
        rows = obj.pin_board_memberships.all()
        out = []
        for row in rows:
            data = BoardSerializer(row.board, context=self.context).data
            data['position'] = row.position
            out.append(data)
        return out

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer_ok = (
            request
            and request.user.is_authenticated
            and request.user.id == instance.author_id
        )
        if not viewer_ok:
            data.pop('scheduled_publish_at', None)
            data.pop('story_expires_at', None)
            data.pop('needs_review', None)
        # Toujours exposer le nom canonique du topic (filtres API / topic=...)
        if instance.topic_id:
            data['topic'] = instance.topic.name
        if request and getattr(instance, 'image', None) and getattr(instance.image, 'name', None):
            data['image'] = build_versioned_media_url(request, instance.image)
        return data

    def validate(self, attrs):
        request = self.context.get('request')
        if 'scheduled_publish_at' in attrs:
            scheduled = attrs['scheduled_publish_at']
            if scheduled is not None:
                if not request or not request.user.is_authenticated:
                    raise serializers.ValidationError({'scheduled_publish_at': 'Authentication required.'})
                if request.user.profile.subscription_plan != Profile.PLAN_PRO:
                    raise serializers.ValidationError({
                        'scheduled_publish_at': 'Scheduled publishing requires Pro plan.',
                    })
                if scheduled <= timezone.now():
                    raise serializers.ValidationError({
                        'scheduled_publish_at': 'Scheduled time must be in the future.',
                    })
        req = self.context.get('request')
        method = getattr(req, 'method', '') if req else ''
        if method == 'POST':
            image = attrs.get('image')
            vid = attrs.get('story_video')
            pub = self._normalize_string_list(attrs.get('public_tags_input', []))
            priv = self._normalize_string_list(attrs.get('private_tags_input', []))
            validate_pin_text(
                attrs.get('title', '') or '',
                attrs.get('description', '') or '',
                pub,
                priv,
            )
            if not image and not vid:
                raise serializers.ValidationError({
                    'non_field_errors': ['Ajoutez une image ou une vidéo story.'],
                })
            raw_story = attrs.get('is_story', False)
            is_story = raw_story is True or str(raw_story).lower() in ('true', '1', 'yes')
            if vid and is_story:
                raise serializers.ValidationError({
                    'story_video': 'Les pins au format story ne peuvent pas inclure de vidéo (image uniquement).',
                })
            profile = req.user.profile if req and req.user.is_authenticated else None
            if method == 'POST' and profile and not profile_can_publish_content(profile):
                raise serializers.ValidationError({
                    'non_field_errors': [
                        'La publication de contenu est réservée aux utilisateurs de 18 ans et plus. '
                        'Les comptes de 13 à 17 ans peuvent consulter et interagir sans publier.',
                    ],
                })
            if profile and (image or vid):
                if not getattr(profile, 'birth_date', None):
                    raise serializers.ValidationError({
                        'non_field_errors': [
                            'La date de naissance est obligatoire pour publier une image ou une vidéo.',
                        ],
                    })
            blur_flag = attrs.get('media_sensitive_blur', False)
            if blur_flag is True or str(blur_flag).lower() in ('true', '1', 'yes'):
                attrs['media_sensitive_blur'] = True
                if not profile or not profile_is_verified_adult(profile):
                    raise serializers.ValidationError({
                        'media_sensitive_blur': [
                            'Réservé aux comptes adultes vérifiés (≥18 ans, date de naissance renseignée).',
                        ],
                    })
            else:
                attrs['media_sensitive_blur'] = False
        if method in ('PUT', 'PATCH') and self.instance:
            title_v = attrs.get('title', self.instance.title)
            desc_v = attrs.get('description', self.instance.description)
            pub_patch = (
                self._normalize_string_list(attrs['public_tags_input'])
                if 'public_tags_input' in attrs
                else None
            )
            priv_patch = (
                self._normalize_string_list(attrs['private_tags_input'])
                if 'private_tags_input' in attrs
                else None
            )
            if 'title' in attrs or 'description' in attrs or pub_patch is not None or priv_patch is not None:
                validate_pin_text(
                    title_v or '',
                    desc_v or '',
                    pub_patch if pub_patch is not None else [],
                    priv_patch if priv_patch is not None else [],
                )
            if 'media_sensitive_blur' in attrs:
                profile = req.user.profile if req and req.user.is_authenticated else None
                want_blur = attrs.get('media_sensitive_blur')
                if want_blur is True or str(want_blur).lower() in ('true', '1', 'yes'):
                    if not profile or not profile_is_verified_adult(profile):
                        raise serializers.ValidationError({
                            'media_sensitive_blur': [
                                'Réservé aux comptes adultes vérifiés (≥18 ans, date de naissance renseignée).',
                            ],
                        })
                    attrs['media_sensitive_blur'] = True
                else:
                    attrs['media_sensitive_blur'] = False
        if method in ('PUT', 'PATCH') and self.instance:
            pin = self.instance
            merged_story = attrs.get('is_story', pin.is_story)
            merged_story = merged_story is True or str(merged_story).lower() in ('true', '1', 'yes')
            vid_up = attrs.get('story_video', serializers.empty)
            new_video = vid_up is not serializers.empty and bool(vid_up)
            if merged_story and new_video:
                raise serializers.ValidationError({
                    'story_video': ['Les pins story ne peuvent pas inclure de vidéo.'],
                })
            if merged_story and pin.story_video and getattr(pin.story_video, 'name', '') and vid_up is serializers.empty:
                raise serializers.ValidationError({
                    'is_story': [
                        'Ce pin contient encore une vidéo : retirez-la (remplacez le média) avant d’activer le format story.',
                    ],
                })
        return attrs

    def get_is_liked(self, obj):
        annotated = getattr(obj, '_is_liked', None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Like.objects.filter(user=request.user, pin=obj).exists()
        return False

    def get_can_comment(self, obj):
        annotated = getattr(obj, '_can_comment', None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        return user_can_comment_on_pin(obj, user)

    def get_is_saved(self, obj):
        annotated = getattr(obj, '_is_saved', None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Save.objects.filter(user=request.user, pin=obj).exists()
        return False

    def get_viewer_has_reported(self, obj):
        v = getattr(obj, '_viewer_has_reported_pin', None)
        if v is not None:
            return bool(v)
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return ContentReport.objects.filter(reporter=request.user, pin=obj).exists()

    def get_is_boosted(self, obj):
        annotated = getattr(obj, '_is_boosted', None)
        if annotated is not None:
            return bool(annotated)
        from monetization.models import PinBoost
        from django.utils import timezone

        now = timezone.now()
        return PinBoost.objects.filter(
            pin=obj,
            status=PinBoost.STATUS_ACTIVE,
            ends_at__gt=now,
        ).exists()

    def get_hashtags(self, obj):
        return [f"#{h.name}" for h in obj.hashtags.all()]

    def get_private_tags(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        if request.user != obj.author:
            return []
        return list(
            PrivatePinTag.objects.filter(pin=obj, user=request.user)
            .values_list('tag', flat=True)
            .order_by('tag')
        )

    def get_topic_meta(self, obj):
        if not obj.topic:
            return None
        request = self.context.get('request')
        lang = resolve_topic_language(request)
        canonical = obj.topic.name
        cache = self.context.setdefault('_topic_translation_cache', {})
        if canonical not in cache:
            cache[canonical] = ensure_topic_translation(canonical, lang)
        display, translations = cache[canonical]
        return {
            'name': display,
            'originalName': canonical,
            'slug': obj.topic.slug,
            'icon': obj.topic.icon,
            'color': obj.topic.color,
            'translations': translations,
        }

    def _resolve_topic(self, topic_value):
        name = (topic_value or '').strip()
        if not name:
            return None
        topic = Topic.objects.filter(slug=name).first()
        if topic:
            return topic
        topic = Topic.objects.filter(name__iexact=name).first()
        if topic:
            return topic
        topic = Topic.objects.create(name=name)
        warm_topic_translations_for_new_topic(name)
        return topic

    def _normalize_string_list(self, raw):
        if raw in (None, ''):
            return []
        if isinstance(raw, str):
            cleaned = raw.strip()
            if cleaned.startswith('[') and cleaned.endswith(']'):
                import json
                try:
                    decoded = json.loads(cleaned)
                    if isinstance(decoded, list):
                        return [str(item).strip() for item in decoded if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in cleaned.split(',') if part.strip()]
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []

    def _normalize_int_list(self, raw):
        values = self._normalize_string_list(raw)
        normalized = []
        for value in values:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                continue
        return normalized

    def _apply_pin_tags_and_boards(self, pin, request, private_tags, public_tags, board_ids):
        extracted_hashtags = extract_hashtags(f"{pin.title} {pin.description}")
        explicit_public_tags = [tag.lstrip('#').lower() for tag in public_tags if tag]
        merged_tags = sorted(set(extracted_hashtags + explicit_public_tags))
        if merged_tags:
            hashtag_objs = []
            for tag in merged_tags:
                hashtag, _ = Hashtag.objects.get_or_create(name=tag)
                hashtag_objs.append(hashtag)
            pin.hashtags.set(hashtag_objs)

        if request and request.user.is_authenticated and private_tags:
            for tag in private_tags:
                cleaned = tag.strip()
                if cleaned:
                    PrivatePinTag.objects.get_or_create(user=request.user, pin=pin, tag=cleaned)

        if request and request.user.is_authenticated and board_ids is not None:
            user_boards_list = list(Board.objects.filter(user=request.user, id__in=board_ids))
            order_map = {bid: i for i, bid in enumerate(board_ids)}
            user_boards_list.sort(key=lambda b: order_map.get(b.id, 999))
            PinBoard.objects.filter(pin=pin).delete()
            for idx, board in enumerate(user_boards_list):
                PinBoard.objects.create(pin=pin, board=board, position=idx)

    def create(self, validated_data):
        private_tags = self._normalize_string_list(validated_data.pop('private_tags_input', []))
        public_tags = self._normalize_string_list(validated_data.pop('public_tags_input', []))
        board_ids = self._normalize_int_list(validated_data.pop('board_ids_input', []))
        topic_value = validated_data.pop('topic', '')
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            raw_story = request.data.get('is_story')
            story_flag = pin_is_story_flag(raw_story, validated_data.get('is_story'))
            apply_pin_creation_rate_limits(request.user.id, story_flag)
            enforce_identical_content_flood(
                request.user.id,
                'pin',
                pin_body_fingerprint(
                    validated_data.get('title', '') or '',
                    validated_data.get('description', '') or '',
                ),
            )
        if request and request.user.is_authenticated and private_tags:
            if not request.user.profile.can_use_private_tags:
                raise serializers.ValidationError({
                    'private_tags_input': 'Private tags require Plus or Pro plan.'
                })
        if request and request.user.is_authenticated:
            validated_data['author'] = request.user
        validated_data['topic'] = self._resolve_topic(topic_value)
        with transaction.atomic():
            pin = super().create(validated_data)
            if request and request.user.is_authenticated:
                apply_server_visual_moderation_to_pin(pin, request.user.profile)
            self._apply_pin_tags_and_boards(pin, request, private_tags, public_tags, board_ids)
        return pin

    def update(self, instance, validated_data):
        board_ids_raw = validated_data.pop('board_ids_input', serializers.empty)
        public_tags = self._normalize_string_list(validated_data.pop('public_tags_input', []))
        private_tags = self._normalize_string_list(validated_data.pop('private_tags_input', []))
        old_img_name = getattr(instance.image, 'name', '') if getattr(instance, 'image', None) else ''
        old_vid_name = getattr(instance.story_video, 'name', '') if getattr(instance, 'story_video', None) else ''
        if 'topic' in validated_data:
            topic_value = validated_data.pop('topic')
            validated_data['topic'] = self._resolve_topic(topic_value)
        with transaction.atomic():
            pin = super().update(instance, validated_data)
            request = self.context.get('request')
            if not request or request.user != pin.author:
                return pin
            if private_tags and not request.user.profile.can_use_private_tags:
                raise serializers.ValidationError({
                    'private_tags_input': 'Private tags require Plus or Pro plan.',
                })
            new_img_name = getattr(pin.image, 'name', '') if getattr(pin, 'image', None) else ''
            new_vid_name = getattr(pin.story_video, 'name', '') if getattr(pin, 'story_video', None) else ''
            if new_img_name != old_img_name or new_vid_name != old_vid_name:
                apply_server_visual_moderation_to_pin(pin, request.user.profile)
            req_data = getattr(request, 'data', {}) or {}
            tag_touch = 'public_tags_input' in req_data or 'private_tags_input' in req_data
            board_ids_list = None
            if board_ids_raw is not serializers.empty:
                board_ids_list = self._normalize_int_list(board_ids_raw)
            if tag_touch or board_ids_list is not None:
                boards_arg = board_ids_list
                if boards_arg is None:
                    boards_arg = list(
                        PinBoard.objects.filter(pin=pin).order_by('position').values_list('board_id', flat=True)
                    )
                self._apply_pin_tags_and_boards(pin, request, private_tags, public_tags, boards_arg)
        return pin


class StandaloneStoryCreateSerializer(serializers.Serializer):
    """POST minimal story Plus/Pro sans pin persistant en grille après 24h."""

    image = serializers.ImageField(required=False, allow_null=True)
    story_video = serializers.FileField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    media_sensitive_blur = serializers.BooleanField(required=False, default=False)

    def validate_image(self, value):
        return _secure_pin_image_upload(value, self.context.get('request'))

    def validate_story_video(self, value):
        return _secure_story_video_upload(value, self.context.get('request'))

    def validate(self, attrs):
        image = attrs.get('image')
        story_video = attrs.get('story_video')
        if image and story_video:
            raise serializers.ValidationError({
                'non_field_errors': ['Choisissez une image ou une vidéo, pas les deux.'],
            })
        if not image and not story_video:
            raise serializers.ValidationError({
                'non_field_errors': ['Ajoutez une image ou une vidéo pour la story éphémère.'],
            })

        request = self.context.get('request')
        profile = request.user.profile if request and request.user.is_authenticated else None
        if not profile or not getattr(profile, 'birth_date', None):
            raise serializers.ValidationError({
                'non_field_errors': [
                    'La date de naissance est obligatoire pour publier une image ou une vidéo.',
                ],
            })

        blur = attrs.get('media_sensitive_blur', False)
        if blur is True or str(blur).lower() in ('true', '1', 'yes'):
            if not profile_is_verified_adult(profile):
                raise serializers.ValidationError({
                    'media_sensitive_blur': [
                        'Réservé aux comptes adultes vérifiés (≥18 ans, date renseignée).',
                    ],
                })
            attrs['media_sensitive_blur'] = True
        else:
            attrs['media_sensitive_blur'] = False

        return attrs


class BoardDetailSerializer(BoardSerializer):
    pins = serializers.SerializerMethodField()
    viewer_can_manage = serializers.SerializerMethodField()
    share_token = serializers.SerializerMethodField()

    class Meta(BoardSerializer.Meta):
        fields = list(BoardSerializer.Meta.fields) + ['pins', 'viewer_can_manage', 'share_token']

    def get_viewer_can_manage(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        u = request.user
        return obj.user_id == u.id or obj.collaborators.filter(id=u.id).exists()

    def get_share_token(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        if obj.user_id != request.user.id:
            return None
        return str(obj.share_token) if obj.share_token else None

    def get_pins(self, obj):
        from .visibility import pin_is_visible_for_request

        request = self.context.get('request')
        links = (
            PinBoard.objects.filter(board=obj)
            .select_related('pin', 'pin__author', 'pin__author__profile', 'pin__topic')
            .prefetch_related('pin__hashtags', 'pin__boards')
            .order_by('position', 'id')
        )
        out = []
        for row in links:
            if not pin_is_visible_for_request(row.pin, request):
                continue
            out.append(PinSerializer(row.pin, context=self.context).data)
        return out
