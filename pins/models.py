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
    collaborators = models.ManyToManyField(User, blank=True, related_name='collaborative_boards')
    # Accès lecture invité (?share=…) pour tableaux privés
    share_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Topic(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    color = models.CharField(max_length=80, default='#6B7280')
    icon = models.CharField(max_length=50, default='category')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or 'topic'
            slug = base
            index = 1
            while Topic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Pin(models.Model):
    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_FOLLOWERS = 'followers'
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_CHOICES = [
        (VISIBILITY_PUBLIC, 'Public'),
        (VISIBILITY_FOLLOWERS, 'Followers'),
        (VISIBILITY_PRIVATE, 'Private'),
    ]

    COMMENTS_OPEN = 'open'
    COMMENTS_FOLLOWERS_ONLY = 'followers_only'
    COMMENTS_CLOSED = 'closed'
    COMMENTS_POLICY_CHOICES = [
        (COMMENTS_OPEN, 'Open'),
        (COMMENTS_FOLLOWERS_ONLY, 'Followers only'),
        (COMMENTS_CLOSED, 'Closed'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    description = models.TextField(blank=True, max_length=1000)
    link = models.URLField(blank=True, default='')
    image = models.ImageField(upload_to='pins/', null=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pins')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='pins')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PUBLIC)
    comments_policy = models.CharField(
        max_length=24,
        choices=COMMENTS_POLICY_CHOICES,
        default=COMMENTS_OPEN,
    )
    certified_credit = models.BooleanField(default=False)
    provenance_root_hash = models.CharField(max_length=128, blank=True)
    boards = models.ManyToManyField(Board, blank=True, related_name='pins', through='PinBoard')
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name='pins')
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True)
    is_story = models.BooleanField(default=False)
    story_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    story_video = models.FileField(upload_to='story_videos/', null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    report_count = models.PositiveIntegerField(default=0)
    moderation_hidden = models.BooleanField(default=False)
    # Image/vidéo : affichage flouté par défaut pour les spectateurs adultes (NSFWJS côté client).
    media_sensitive_blur = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def refresh_story_expiry(self):
        from datetime import timedelta
        from django.utils import timezone

        if not self.is_story:
            self.story_expires_at = None
            return
        now = timezone.now()
        if self.scheduled_publish_at and self.scheduled_publish_at > now:
            base = self.scheduled_publish_at
        else:
            base = now
        self.story_expires_at = base + timedelta(hours=24)

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

    @property
    def topic_name(self):
        return self.topic.name if self.topic else ''

class PinVariant(models.Model):
    """Crops / ratios alternatifs pour un même pin (story 9:16, carré, paysage). Une ligne métier unique."""
    KIND_STORY = 'story'
    KIND_SQUARE = 'square'
    KIND_LANDSCAPE = 'landscape'
    KIND_CHOICES = [
        (KIND_STORY, 'Story'),
        (KIND_SQUARE, 'Square'),
        (KIND_LANDSCAPE, 'Landscape'),
    ]

    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='variant_assets')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    image = models.ImageField(upload_to='pins/variants/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['pin', 'kind']]
        ordering = ['kind']

    def __str__(self):
        return f'{self.pin_id}:{self.kind}'


class PinBoard(models.Model):
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='pin_board_memberships')
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='pin_board_memberships')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [['pin', 'board']]
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.pin_id}->{self.board_id}@{self.position}'


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
    hidden_by_owner = models.BooleanField(default=False)
    text = models.TextField()
    gif_url = models.URLField(blank=True, null=True)
    media = models.ImageField(upload_to='comments/', blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name='replies', blank=True, null=True)
    mentions = models.JSONField(default=list, blank=True)
    original_language = models.CharField(max_length=8, default='auto')
    translated_text = models.TextField(blank=True)
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name='comments')
    created_at = models.DateTimeField(auto_now_add=True)
    needs_review = models.BooleanField(default=False)
    report_count = models.PositiveIntegerField(default=0)
    moderation_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    @property
    def likes_count(self):
        return self.comment_likes.count()


class ContentReport(models.Model):
    """Signalement utilisateur (pin ou commentaire)."""

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='content_reports')
    pin = models.ForeignKey(Pin, null=True, blank=True, on_delete=models.CASCADE, related_name='reports')
    comment = models.ForeignKey(
        'Comment',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='reports',
    )
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['pin', '-created_at']),
            models.Index(fields=['comment', '-created_at']),
        ]

    def __str__(self):
        if self.pin_id:
            return f'report pin {self.pin_id} by {self.reporter_id}'
        return f'report comment {self.comment_id} by {self.reporter_id}'


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


class TopicTranslation(models.Model):
    topic = models.CharField(max_length=120, unique=True)
    translations = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['topic']

    def __str__(self):
        return self.topic


class PinViewEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pin_view_events')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='view_events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SearchInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_interactions')
    query = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
