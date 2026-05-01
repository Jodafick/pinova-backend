from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Hashtag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"#{self.name}"


class Board(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='boards')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-created_at']

    @property
    def pin_count(self):
        return self.pins.count()

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Pin(models.Model):
    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_FOLLOWERS = 'followers'
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_CHOICES = [
        (VISIBILITY_PUBLIC, 'Public'),
        (VISIBILITY_FOLLOWERS, 'Followers'),
        (VISIBILITY_PRIVATE, 'Private'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='pins/')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pins')
    topic = models.CharField(max_length=100, default='Général')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PUBLIC)
    certified_credit = models.BooleanField(default=False)
    provenance_root_hash = models.CharField(max_length=128, blank=True)
    boards = models.ManyToManyField(Board, blank=True, related_name='pins')
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name='pins')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            # Ensure unique slug
            original_slug = self.slug
            count = 1
            while Pin.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{count}"
                count += 1
        super().save(*args, **kwargs)

    @property
    def likes_count(self):
        return self.likes.count()

    @property
    def comments_count(self):
        return self.comments.count()

    @property
    def saves_count(self):
        return self.saves.count()

class Save(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saves')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='saves')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pin')

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='likes')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pin')

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    gif_url = models.URLField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name='replies', blank=True, null=True)
    mentions = models.JSONField(default=list, blank=True)
    original_language = models.CharField(max_length=8, default='auto')
    translated_text = models.TextField(blank=True)
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name='comments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def likes_count(self):
        return self.comment_likes.count()


class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_likes')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='comment_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')


class PrivatePinTag(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='private_pin_tags')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='private_tags')
    tag = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pin', 'tag')
        ordering = ['tag']

    def __str__(self):
        return f"{self.user.username}: {self.tag}"


class PinProvenanceEvent(models.Model):
    ACTION_CREATE = 'create'
    ACTION_EDIT = 'edit'
    ACTION_SAVE = 'save'
    ACTION_REPOST = 'repost'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_EDIT, 'Edit'),
        (ACTION_SAVE, 'Save'),
        (ACTION_REPOST, 'Repost'),
    ]

    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='provenance_events')
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='provenance_events')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default=ACTION_CREATE)
    previous_hash = models.CharField(max_length=128, blank=True)
    current_hash = models.CharField(max_length=128)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.pin_id}:{self.action}:{self.current_hash[:12]}"
