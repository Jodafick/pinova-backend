from rest_framework import serializers
import re
from django.db.models import Count, Case, When, Value, IntegerField, Exists, OuterRef
from django.utils import timezone
from .models import (
    Pin,
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

from accounts.models import Profile
from accounts.serializers import ProfileSerializer
from .comment_access import viewer_sees_comment_content, user_can_comment_on_pin
from .visibility import profile_is_verified_adult
from .moderation import (
    validate_pin_text,
    apply_pin_creation_rate_limits,
    pin_body_fingerprint,
    enforce_identical_content_flood,
    pin_is_story_flag,
)
from .topic_i18n import resolve_topic_language, ensure_topic_translation, warm_topic_translations_for_new_topic


HASHTAG_RE = re.compile(r'#([A-Za-z0-9_]{2,80})')
MENTION_RE = re.compile(r'@([A-Za-z0-9_\.]{2,80})')


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
            url = img.url
            urls.append(request.build_absolute_uri(url))
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
        url = avatar.url
        if request:
            return request.build_absolute_uri(url)
        return url

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
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    saves_count = serializers.IntegerField(read_only=True)
    can_comment = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    viewer_has_reported = serializers.SerializerMethodField()
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
            'is_liked',
            'is_saved',
            'viewer_has_reported',
            'media_sensitive_blur',
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
        url = obj.story_video.url
        return request.build_absolute_uri(url) if request else url

    def validate_story_video(self, value):
        if not value:
            return value
        ct = (getattr(value, 'content_type', '') or '').split(';')[0].strip().lower()
        allowed = frozenset({'video/mp4', 'video/webm', 'video/quicktime'})
        if ct not in allowed:
            raise serializers.ValidationError('Unsupported video type (use MP4, WebM or MOV).')
        max_bytes = 48 * 1024 * 1024
        if getattr(value, 'size', 0) > max_bytes:
            raise serializers.ValidationError('Video too large (max 48 MB).')
        return value

    def get_boards(self, obj):
        rows = (
            PinBoard.objects.filter(pin=obj)
            .select_related('board')
            .order_by('position', 'id')
        )
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
            if vid and not is_story:
                raise serializers.ValidationError({'is_story': 'Story video requires is_story=true.'})
            profile = req.user.profile if req and req.user.is_authenticated else None
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
            if 'title' in attrs or 'description' in attrs:
                validate_pin_text(title_v or '', desc_v or '')
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
        return attrs

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Like.objects.filter(user=request.user, pin=obj).exists()
        return False

    def get_can_comment(self, obj):
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        return user_can_comment_on_pin(obj, user)

    def get_is_saved(self, obj):
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
        pin = super().create(validated_data)
        self._apply_pin_tags_and_boards(pin, request, private_tags, public_tags, board_ids)
        return pin

    def update(self, instance, validated_data):
        board_ids = validated_data.pop('board_ids_input', serializers.empty)
        if 'topic' in validated_data:
            topic_value = validated_data.pop('topic')
            validated_data['topic'] = self._resolve_topic(topic_value)
        pin = super().update(instance, validated_data)
        request = self.context.get('request')
        if board_ids is not serializers.empty and request and request.user == pin.author:
            self._apply_pin_tags_and_boards(
                pin,
                request,
                [],
                [],
                self._normalize_int_list(board_ids),
            )
        return pin


EPHEMERAL_STORY_VIDEO_MAX_BYTES = 48 * 1024 * 1024
EPHEMERAL_STORY_VIDEO_CT = frozenset({'video/mp4', 'video/webm', 'video/quicktime'})


class StandaloneStoryCreateSerializer(serializers.Serializer):
    """POST minimal story Plus/Pro sans pin persistant en grille après 24h."""

    image = serializers.ImageField(required=False, allow_null=True)
    story_video = serializers.FileField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    media_sensitive_blur = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        image = attrs.get('image')
        vid = attrs.get('story_video')
        if image and vid:
            raise serializers.ValidationError({
                'non_field_errors': ['Une seule vue : image ou vidéo pour la story éphémère.'],
            })
        if not image and not vid:
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

        if vid:
            ct = (getattr(vid, 'content_type', '') or '').split(';')[0].strip().lower()
            if ct not in EPHEMERAL_STORY_VIDEO_CT:
                raise serializers.ValidationError({'story_video': 'Formats acceptés : MP4, WebM, MOV.'})
            if getattr(vid, 'size', 0) > EPHEMERAL_STORY_VIDEO_MAX_BYTES:
                raise serializers.ValidationError({'story_video': 'Vidéo trop lourde (max 48 Mo).'})

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
