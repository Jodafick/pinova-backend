from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

from .report_constants import REPORT_CATEGORY_CHOICES
from .storage_media import unlink_field_file


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
    cover_image = models.ImageField(upload_to='topic_covers/', null=True, blank=True)
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
    updated_at = models.DateTimeField(auto_now=True)
    # Incrément / contrôle de fraîcheur (sync client, cache) — défaut 1 si la colonne existe déjà en BDD.
    version = models.PositiveIntegerField(default=1)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True)
    is_story = models.BooleanField(default=False)
    # Plus/Pro « story éphémère » : après 24h la ligne est détruite (pas d’archive en pin grille).
    story_ephemeral = models.BooleanField(default=False, db_index=True)
    story_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    story_video = models.FileField(upload_to='story_videos/', null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    report_count = models.PositiveIntegerField(default=0)
    moderation_hidden = models.BooleanField(default=False)
    # Image/vidéo : affichage flouté par défaut pour les spectateurs adultes (NSFWJS côté client).
    media_sensitive_blur = models.BooleanField(default=False)
    # Partages enregistrés (POST record-share) — dénormalisé pour l’API mobile / détail.
    shares_count = models.PositiveIntegerField(default=0)
    upload_idempotency_key = models.CharField(max_length=128, blank=True, default='', db_index=True)

    def __str__(self):
        return self.title

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['author', 'upload_idempotency_key'],
                condition=~models.Q(upload_idempotency_key=''),
                name='unique_pin_upload_idempotency_per_author',
            ),
        ]

    def refresh_story_expiry(self):
        from datetime import timedelta
        from django.utils import timezone

        if not self.is_story:
            self.story_expires_at = None
            return
        # Seules les stories « éphémères » (standalone Plus/Pro) ont une date d’expiration.
        # Un pin classique en format story reste archivé comme un pin normal (pas de 24h).
        if not self.story_ephemeral:
            self.story_expires_at = None
            return
        now = timezone.now()
        if self.scheduled_publish_at and self.scheduled_publish_at > now:
            base = self.scheduled_publish_at
        else:
            base = now
        self.story_expires_at = base + timedelta(hours=24)

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                prev = Pin.objects.only('image', 'story_video').get(pk=self.pk)
            except Pin.DoesNotExist:
                prev = None
            if prev is not None:
                prev_img = prev.image.name if prev.image else ''
                new_img = self.image.name if self.image else ''
                if prev_img and prev_img != new_img:
                    unlink_field_file(prev.image)
                prev_vid = prev.story_video.name if prev.story_video else ''
                new_vid = self.story_video.name if self.story_video else ''
                if prev_vid and prev_vid != new_vid:
                    unlink_field_file(prev.story_video)

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

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = PinVariant.objects.only('image').get(pk=self.pk)
            except PinVariant.DoesNotExist:
                old = None
            if old is not None:
                old_nm = old.image.name if old.image else ''
                new_nm = self.image.name if self.image else ''
                if old_nm and old_nm != new_nm:
                    unlink_field_file(old.image)
        super().save(*args, **kwargs)


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
    updated_at = models.DateTimeField(auto_now=True)
    needs_review = models.BooleanField(default=False)
    report_count = models.PositiveIntegerField(default=0)
    moderation_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = Comment.objects.only('media').get(pk=self.pk)
            except Comment.DoesNotExist:
                old = None
            if old is not None:
                old_nm = old.media.name if old.media else ''
                new_nm = self.media.name if self.media else ''
                if old_nm and old_nm != new_nm:
                    unlink_field_file(old.media)
        super().save(*args, **kwargs)

    @property
    def likes_count(self):
        return self.comment_likes.count()


class ContentReport(models.Model):
    """Signalement utilisateur (profil, pin / story, commentaire)."""

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='content_reports')
    pin = models.ForeignKey(Pin, null=True, blank=True, on_delete=models.CASCADE, related_name='reports')
    comment = models.ForeignKey(
        'Comment',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='reports',
    )
    reported_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='profile_reports_received',
    )
    category = models.CharField(max_length=32, choices=REPORT_CATEGORY_CHOICES, default='other')
    details = models.TextField(blank=True)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['pin', '-created_at']),
            models.Index(fields=['comment', '-created_at']),
            models.Index(fields=['reported_user', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(pin__isnull=False, comment__isnull=True, reported_user__isnull=True)
                    | models.Q(pin__isnull=True, comment__isnull=False, reported_user__isnull=True)
                    | models.Q(pin__isnull=True, comment__isnull=True, reported_user__isnull=False)
                ),
                name='contentreport_exactly_one_target',
            ),
            models.UniqueConstraint(
                fields=['reporter', 'reported_user'],
                condition=models.Q(reported_user__isnull=False),
                name='contentreport_unique_profile_per_reporter',
            ),
            models.UniqueConstraint(
                fields=['reporter', 'pin'],
                condition=models.Q(pin__isnull=False),
                name='contentreport_unique_pin_per_reporter',
            ),
            models.UniqueConstraint(
                fields=['reporter', 'comment'],
                condition=models.Q(comment__isnull=False),
                name='contentreport_unique_comment_per_reporter',
            ),
        ]

    def __str__(self):
        if self.pin_id:
            return f'report pin {self.pin_id} by {self.reporter_id}'
        if self.comment_id:
            return f'report comment {self.comment_id} by {self.reporter_id}'
        return f'report profile {self.reported_user_id} by {self.reporter_id}'


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


class PinEmbedding(models.Model):
    pin = models.OneToOneField(Pin, on_delete=models.CASCADE, related_name='embedding_profile')
    embedding = models.JSONField(default=list, blank=True)
    embedding_dim = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class UserEmbedding(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='embedding_profile')
    embedding = models.JSONField(default=list, blank=True)
    embedding_dim = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class UserInteraction(models.Model):
    TYPE_VIEW = 'view'
    TYPE_LIKE = 'like'
    TYPE_CLICK = 'click'
    TYPE_SAVE = 'save'
    TYPE_SHARE = 'share'
    TYPE_CREATOR_VISIT = 'creator_visit'
    EVENT_TYPE_CHOICES = [
        (TYPE_VIEW, 'View'),
        (TYPE_LIKE, 'Like'),
        (TYPE_CLICK, 'Click'),
        (TYPE_SAVE, 'Save'),
        (TYPE_SHARE, 'Share'),
        (TYPE_CREATOR_VISIT, 'Creator Visit'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pin_interactions')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='user_interactions', null=True, blank=True)
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='creator_interactions')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    dwell_seconds = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]


class TagInvisible(models.Model):
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='invisible_tags')
    tag = models.CharField(max_length=100)
    confidence = models.FloatField(default=0.0)
    source = models.CharField(max_length=30, default='auto')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('pin', 'tag')
        ordering = ['-confidence', 'tag']


class LegalDocument(models.Model):
    """Contenu des pages publiques : confidentialité, CGU, contact (titres + corps multilingue)."""

    SLUG_PRIVACY = 'privacy'
    SLUG_TERMS = 'terms'
    SLUG_CONTACT = 'contact'
    SLUG_CHOICES = [
        (SLUG_PRIVACY, 'Politique de confidentialité'),
        (SLUG_TERMS, "Conditions d'utilisation"),
        (SLUG_CONTACT, 'Contact'),
    ]

    slug = models.CharField(max_length=40, choices=SLUG_CHOICES, unique=True)
    title_fr = models.CharField('Titre (FR)', max_length=500, blank=True, default='')
    title_en = models.CharField('Titre (EN)', max_length=500, blank=True, default='')
    body_fr = models.TextField(blank=True, default='')
    body_en = models.TextField(blank=True, default='')
    contact_email = models.EmailField(
        'E-mail de contact',
        blank=True,
        default='',
        help_text='Utilisé pour la page « contact » (mailto).',
    )
    translations_cache = models.JSONField(
        'Cache traductions',
        default=dict,
        blank=True,
        help_text='Rempli automatiquement (googletrans), ex. {"es": {"title": "…", "body": "…"}}.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slug']
        verbose_name = 'Page publique (légal / contact)'
        verbose_name_plural = 'Pages publiques (légal / contact)'

    def __str__(self):
        return self.slug


class FaqItem(models.Model):
    """Questions / réponses affichées sur la page FAQ (FR/EN), avec lien optionnel vers une page légale."""

    RELATED_NONE = ''
    RELATED_SLUG_CHOICES = [
        (RELATED_NONE, 'Aucun lien'),
        (LegalDocument.SLUG_PRIVACY, 'Confidentialité'),
        (LegalDocument.SLUG_TERMS, "Conditions d'utilisation"),
        (LegalDocument.SLUG_CONTACT, 'Contact'),
    ]

    question_fr = models.CharField('Question (FR)', max_length=500)
    question_en = models.CharField('Question (EN)', max_length=500, blank=True, default='')
    answer_fr = models.TextField('Réponse (FR)')
    answer_en = models.TextField('Réponse (EN)', blank=True, default='')
    sort_order = models.PositiveSmallIntegerField('Ordre', default=0)
    is_published = models.BooleanField('Publié', default=True, db_index=True)
    related_legal_slug = models.CharField(
        'Lien « en savoir plus »',
        max_length=40,
        blank=True,
        default='',
        choices=RELATED_SLUG_CHOICES,
    )

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Entrée FAQ'
        verbose_name_plural = 'FAQ'

    def __str__(self):
        return (self.question_fr or self.question_en or '')[:80]


class BoardCollaborationInvite(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
    ]

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='collaboration_invites')
    invitee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_collab_invites_received')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_collab_invites_sent')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['board', 'invitee'], name='unique_board_collab_invitee'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.board_id} -> {self.invitee_id} ({self.status})'
