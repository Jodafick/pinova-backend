from rest_framework import serializers
import re
from .models import (
    Pin,
    Comment,
    Like,
    Save,
    Board,
    Hashtag,
    PrivatePinTag,
    PinProvenanceEvent,
)

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

    class Meta:
        model = Board
        fields = ['id', 'name', 'description', 'is_private', 'created_at', 'pin_count']


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
    hashtags = serializers.SerializerMethodField()

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
            'parent',
            'mentions',
            'hashtags',
            'original_language',
            'translated_text',
            'created_at',
            'replies',
        ]
        read_only_fields = ['mentions', 'hashtags', 'translated_text', 'replies']

    def get_replies(self, obj):
        replies = obj.replies.all().select_related('user', 'user__profile')
        return CommentSerializer(replies, many=True, context=self.context).data

    def get_hashtags(self, obj):
        return [f"#{h.name}" for h in obj.hashtags.all()]

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

    class Meta:
        model = Pin
        fields = [
            'id',
            'slug',
            'title',
            'description',
            'image',
            'author',
            'author_profile',
            'topic',
            'visibility',
            'certified_credit',
            'provenance_root_hash',
            'hashtags',
            'private_tags',
            'private_tags_input',
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
        return list(
            PrivatePinTag.objects.filter(pin=obj, user=request.user)
            .values_list('tag', flat=True)
            .order_by('tag')
        )

    def create(self, validated_data):
        private_tags = validated_data.pop('private_tags_input', [])
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['author'] = request.user
        pin = super().create(validated_data)
        hashtags = extract_hashtags(f"{pin.title} {pin.description}")
        if hashtags:
            hashtag_objs = []
            for tag in hashtags:
                hashtag, _ = Hashtag.objects.get_or_create(name=tag)
                hashtag_objs.append(hashtag)
            pin.hashtags.set(hashtag_objs)
        if request and request.user.is_authenticated and private_tags:
            for tag in private_tags:
                cleaned = tag.strip()
                if cleaned:
                    PrivatePinTag.objects.get_or_create(user=request.user, pin=pin, tag=cleaned)
        return pin
