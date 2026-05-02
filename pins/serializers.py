from rest_framework import serializers
import re
from django.db.models import Count, Case, When, Value, IntegerField
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
)

from accounts.models import Profile
from accounts.serializers import ProfileSerializer


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
    pin_count = serializers.IntegerField(read_only=True)
    collaborator_count = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = ['id', 'name', 'description', 'is_private', 'created_at', 'pin_count', 'collaborator_count']

    def get_collaborator_count(self, obj):
        return obj.collaborators.count()


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
    replies = serializers.SerializerMethodField()
    replies_next_page = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    hashtags = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id',
            'user',
            'username',
            'display_name',
            'avatar_color',
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
            'replies',
            'replies_next_page',
            'replies_count',
        ]
        read_only_fields = ['mentions', 'hashtags', 'translated_text', 'replies']

    def get_replies(self, obj):
        if not self.context.get('include_replies', True):
            return []
        replies_page_size = int(self.context.get('replies_page_size', 3))
        replies_sort = (self.context.get('replies_sort') or 'recent').lower()
        highlighted_comment_id = self.context.get('highlighted_comment_id')
        replies = obj.replies.all().select_related('user', 'user__profile')
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
    boards = BoardSerializer(many=True, read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    saves_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
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

    class Meta:
        model = Pin
        fields = [
            'id',
            'slug',
            'title',
            'description',
            'link',
            'image',
            'author',
            'author_profile',
            'boards',
            'topic',
            'topic_meta',
            'visibility',
            'certified_credit',
            'provenance_root_hash',
            'hashtags',
            'private_tags',
            'private_tags_input',
            'public_tags_input',
            'board_ids_input',
            'created_at',
            'likes_count',
            'comments_count',
            'saves_count',
            'is_liked',
            'is_saved',
        ]
        read_only_fields = ['provenance_root_hash']
        extra_kwargs = {
            'author': {'required': False},
        }

    def validate(self, attrs):
        request = self.context.get('request')
        certified = attrs.get('certified_credit')
        if certified is True:
            if not request or not request.user.is_authenticated:
                raise serializers.ValidationError({'certified_credit': 'Authentication required.'})
            if request.user.profile.subscription_plan != Profile.PLAN_PRO:
                raise serializers.ValidationError({
                    'certified_credit': 'Certified creator credit requires Pro plan.',
                })
        return attrs

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Like.objects.filter(user=request.user, pin=obj).exists()
        return False

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Save.objects.filter(user=request.user, pin=obj).exists()
        return False

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
        return {
            'name': obj.topic.name,
            'slug': obj.topic.slug,
            'icon': obj.topic.icon,
            'color': obj.topic.color,
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

        if request and request.user.is_authenticated and board_ids:
            user_boards = Board.objects.filter(user=request.user, id__in=board_ids)
            if user_boards.exists():
                pin.boards.add(*user_boards)

    def create(self, validated_data):
        private_tags = self._normalize_string_list(validated_data.pop('private_tags_input', []))
        public_tags = self._normalize_string_list(validated_data.pop('public_tags_input', []))
        board_ids = self._normalize_int_list(validated_data.pop('board_ids_input', []))
        topic_value = validated_data.pop('topic', '')
        request = self.context.get('request')
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
        if 'topic' in validated_data:
            topic_value = validated_data.pop('topic')
            validated_data['topic'] = self._resolve_topic(topic_value)
        return super().update(instance, validated_data)
