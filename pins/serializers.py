from rest_framework import serializers
from .models import Pin, Comment, Like, Save, Board

class BoardSerializer(serializers.ModelSerializer):
    pin_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Board
        fields = ['id', 'name', 'description', 'user', 'is_private', 'pin_count', 'created_at']
        read_only_fields = ['user']
from accounts.serializers import ProfileSerializer

class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    display_name = serializers.CharField(source='user.profile.display_name', read_only=True)
    avatar_color = serializers.CharField(source='user.profile.avatar_color', read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'user', 'username', 'display_name', 'avatar_color', 'text', 'created_at']

class PinSerializer(serializers.ModelSerializer):
    author_profile = ProfileSerializer(source='author.profile', read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    saves_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    
    class Meta:
        model = Pin
        fields = ['id', 'title', 'description', 'image', 'author', 'author_profile', 'topic', 'created_at', 'likes_count', 'comments_count', 'saves_count', 'is_liked', 'is_saved']

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
