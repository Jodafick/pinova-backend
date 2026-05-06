from rest_framework import mixins, viewsets, status, permissions, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q, Case, When, Value, IntegerField, Max, OuterRef, Subquery, Exists
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.cache import cache
from django.db import IntegrityError
from datetime import timedelta
from asgiref.sync import async_to_sync
from googletrans import Translator
from pathlib import Path
from urllib.parse import urlencode
from django.conf import settings
from django.core.files.storage import default_storage
from PIL import Image
from accounts.models import Profile
from accounts.blocking import filter_pins_exclude_blocked, blocked_mutual_user_ids
from accounts.subscription_utils import _enforce_subscription_state
from pinova_backend.media_cache import append_version_using_media_path, build_versioned_media_url
from pinova_backend.throttling import client_ip_from_request
import re
import uuid
from collections import OrderedDict
from .models import (
    Pin,
    Topic,
    Comment,
    Like,
    Save,
    Hashtag,
    PrivatePinTag,
    Board,
    CommentLike,
    PinViewEvent,
    SearchInteraction,
    UserInteraction,
    PinBoard,
    ContentReport,
    BoardCollaborationInvite,
    LegalDocument,
)
from .legal_page_i18n import build_legal_api_response
from .faq_api import build_faq_overview_response
from .search_utils import broad_pin_q, fuzzy_score
from .recommendation_engine import rank_recommendations_for_user, update_pin_ai_metadata, update_user_embedding
from .serializers import (
    PinSerializer,
    StandaloneStoryCreateSerializer,
    CommentSerializer,
    BoardSerializer,
    BoardDetailSerializer,
    BoardCollaborationInviteSerializer,
    extract_hashtags,
)
from .comment_media import compress_comment_media_upload
from .visibility import pin_is_visible_for_request, sensitive_pins_query_filter, viewer_is_verified_adult
from .comment_access import user_can_comment_on_pin, viewer_sees_comment_content
from .moderation import (
    sanitize_comment_plain_text,
    validate_comment_text,
    validate_pin_text,
    apply_comment_rate_limit,
    apply_pin_creation_rate_limits,
    comment_body_fingerprint,
    pin_body_fingerprint,
    enforce_identical_content_flood,
    increment_pin_reports,
    increment_comment_reports,
    apply_pin_report_thresholds,
    apply_comment_report_thresholds,
)
from .translation import translate_text_to, detect_original_language
from .topic_i18n import resolve_topic_language, ensure_topic_translation
from .pagination import PinFeedPagination, BoardListPagination
from notifications.models import Notification
from notifications.notification_i18n import create_localized_notification
from .creator_analytics import creator_totals_for_user, paginated_creator_top_pins
from .creator_audience import VALID_ACTIONS, creator_engagement_breakdown
from .weekly_stats import (
    weekly_creator_pins_page,
    pin_thumbnail_absolute_url,
    creator_period_engagement_totals,
)
from .report_constants import REPORT_DETAILS_MAX_LEN, normalize_report_category

# Borne mémoire pour mélange following / discover (home_feed) et tri par score sujet.
FEED_INTERLEAVE_SOURCE_CAP = 2500


def _parse_report_request(request, *, min_details_len: int = 10):
    """Catégorie + texte ; accepte encore `reason` (legacy) si `details` est vide. Retourne None si invalide."""
    category = normalize_report_category(request.data.get('category'))
    details = str(request.data.get('details') or '').strip()[:REPORT_DETAILS_MAX_LEN]
    if not details:
        details = str(request.data.get('reason') or '').strip()[:REPORT_DETAILS_MAX_LEN]
    if len(details) < min_details_len:
        return None
    return category, details


def _pin_download_absolute_url(request, pin, requested_quality, apply_watermark=False):
    """Génère (ou lit le cache) un JPEG export ; filigrane discret pour Plus/Pro."""
    if not pin.image:
        raise ValueError('Pin has no image')
    if requested_quality == 'standard' and not apply_watermark:
        return build_versioned_media_url(request, pin.image)

    variants_dir = Path(settings.MEDIA_ROOT) / 'pin_download_variants'
    variants_dir.mkdir(parents=True, exist_ok=True)
    wm_key = 'wm' if apply_watermark else 'plain'
    filename = f'{pin.id}_{requested_quality}_{wm_key}.jpg'
    out_path = variants_dir / filename
    src_path = Path(pin.image.path)
    max_side = {'standard': 2048, 'hd': 1920, '4k': 3840}[requested_quality]

    needs_write = True
    try:
        if out_path.exists():
            needs_write = out_path.stat().st_mtime < src_path.stat().st_mtime
    except OSError:
        needs_write = True

    if needs_write:
        from .watermark import apply_watermark_rgb

        front = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/') or 'http://localhost:5174'
        with Image.open(src_path) as im:
            im_rgb = im.convert('RGB')
            w, h = im_rgb.size
            longest = max(w, h)
            if longest > max_side:
                scale = max_side / float(longest)
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                im_rgb = im_rgb.resize((nw, nh), Image.Resampling.LANCZOS)
            if apply_watermark:
                lines = [f'@{pin.author.username}', f'{front}/profile/{pin.author.username}']
                im_rgb = apply_watermark_rgb(im_rgb, lines)
            im_rgb.save(out_path, 'JPEG', quality=92, optimize=True)

    media = settings.MEDIA_URL or '/media/'
    if not str(media).endswith('/'):
        media = f'{media}/'
    rel_url = f'{media}pin_download_variants/{filename}'
    base = request.build_absolute_uri(rel_url)
    return append_version_using_media_path(base, relative_under_media=f'pin_download_variants/{filename}')


class CommentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class ReplyPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 30


class PinViewSet(viewsets.ModelViewSet):
    queryset = Pin.objects.all()
    serializer_class = PinSerializer
    lookup_field = 'slug'
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = PinFeedPagination

    def _resolve_target_lang(self, request):
        explicit = request.data.get('target_lang') or request.query_params.get('target_lang')
        if explicit:
            return str(explicit).strip().lower()
        if request.user.is_authenticated:
            return (request.user.profile.preferred_language or 'fr').lower()
        return 'fr'

    def _ordered_by_topic_score(self, queryset, topic_scores, cap=FEED_INTERLEAVE_SOURCE_CAP):
        cap = max(100, min(int(cap), 5000))
        base_qs = queryset.order_by('media_sensitive_blur', '-created_at')[:cap]
        if not topic_scores:
            return list(base_qs)
        items = list(base_qs)
        items.sort(
            key=lambda pin: (
                topic_scores.get(self._pin_topic_name(pin), 0),
                -(1 if pin.media_sensitive_blur else 0),
                pin.created_at.timestamp(),
            ),
            reverse=True,
        )
        return items

    def _pin_topic_name(self, pin):
        return pin.topic.name if getattr(pin, 'topic_id', None) and pin.topic else ''

    def _apply_topic_filter(self, queryset, topic_filter):
        topic_filter = (topic_filter or '').strip()
        if not topic_filter:
            return queryset
        return queryset.filter(Q(topic__slug=topic_filter) | Q(topic__name=topic_filter))

    def _build_topic_scores(self, user):
        scores = {}
        if not user or not user.is_authenticated:
            return scores
        recent_likes = (
            Like.objects.filter(user=user)
            .select_related('pin', 'pin__topic')
            .order_by('-created_at')[:200]
        )
        recent_saves = (
            Save.objects.filter(user=user)
            .select_related('pin', 'pin__topic')
            .order_by('-created_at')[:200]
        )
        recent_views = (
            PinViewEvent.objects.filter(user=user)
            .select_related('pin', 'pin__topic')
            .order_by('-created_at')[:300]
        )
        for item in recent_likes:
            topic = self._pin_topic_name(item.pin)
            if topic:
                scores[topic] = scores.get(topic, 0) + 4
        for item in recent_saves:
            topic = self._pin_topic_name(item.pin)
            if topic:
                scores[topic] = scores.get(topic, 0) + 4
        for item in recent_views:
            topic = self._pin_topic_name(item.pin)
            if topic:
                scores[topic] = scores.get(topic, 0) + 1
        recent_queries = SearchInteraction.objects.filter(user=user).order_by('-created_at')[:100]
        for query in recent_queries:
            q = (query.query or '').strip()
            if not q:
                continue
            for topic in Pin.objects.filter(topic__name__icontains=q).values_list('topic__name', flat=True).distinct()[:20]:
                scores[topic] = scores.get(topic, 0) + 2
        return scores

    def _scheduled_publish_ok_q(self):
        now = timezone.now()
        return Q(scheduled_publish_at__isnull=True) | Q(scheduled_publish_at__lte=now)

    def _story_feed_q(self):
        """Stories éphémères expirées masquées sauf pour l'auteur. Pins story classiques toujours visibles."""
        user = self.request.user if self.request.user.is_authenticated else None
        now = timezone.now()
        q = (
            Q(is_story=False)
            | Q(is_story=True, story_ephemeral=False)
            | Q(is_story=True, story_ephemeral=True, story_expires_at__gt=now)
        )
        if user:
            q |= Q(is_story=True, author=user)
        return q

    def _story_main_feed_placement_q(self):
        """Les stories des autres n'apparaissent pas dans le fil masonry (uniquement bande Stories)."""
        user = self.request.user if self.request.user.is_authenticated else None
        q = Q(is_story=False)
        if user:
            # Stories « classiques » (non éphémères) restent visibles pour l'auteur dans le fil.
            q |= Q(author=user) & (Q(is_story=False) | Q(story_ephemeral=False))
        return q

    def get_queryset(self):
        ephemeral_hide_feed_actions = frozenset({
            'list',
            'discover',
            'header_search',
            'recommendations',
            'following',
            'home_feed',
        })

        def exclude_ephemeral_story_only(qs):
            if getattr(self, 'action', None) in ephemeral_hide_feed_actions:
                return qs.exclude(Q(is_story=True, story_ephemeral=True))
            return qs

        saved_by_me = (self.request.query_params.get('saved_by_me') or '').strip().lower() in ('1', 'true', 'yes')
        if saved_by_me and not self.request.user.is_authenticated:
            return Pin.objects.none()

        queryset = (
            Pin.objects.select_related('author', 'author__profile', 'topic')
            .prefetch_related('hashtags', 'boards', 'variant_assets')
            .all()
            .order_by('media_sensitive_blur', '-created_at')
        )
        profile_author = (self.request.query_params.get('author') or '').strip()
        if saved_by_me:
            profile_author = ''
        if profile_author:
            queryset = queryset.filter(author__username=profile_author)
            # Sur une vue profil (author=...), ne jamais renvoyer un contenu bloqué par modération,
            # y compris pour le propriétaire du profil.
            queryset = queryset.exclude(moderation_hidden=True)
        topic = self.request.query_params.get('topic')
        queryset = self._apply_topic_filter(queryset, topic)
        sched = self._scheduled_publish_ok_q()
        story_q = self._story_feed_q()
        placement_q = self._story_main_feed_placement_q()
        # Ne pas exclure les stories des autres dans retrieve/save/like/etc., sinon 404 sur ces pins.
        story_placement_actions = frozenset({
            'list', 'discover', 'header_search', 'recommendations', 'following', 'home_feed',
        })
        apply_story_placement = (
            getattr(self, 'action', None) in story_placement_actions
            and not profile_author
            and not saved_by_me
        )

        if not self.request.user.is_authenticated:
            core = (
                Q(visibility=Pin.VISIBILITY_PUBLIC, author__profile__private_profile=False)
                & sched
                & story_q
                & Q(moderation_hidden=False)
            )
            if apply_story_placement:
                core &= placement_q
            core &= sensitive_pins_query_filter(self.request)
            return exclude_ephemeral_story_only(queryset.filter(core))

        my_profile = self.request.user.profile
        visibility_q = (
            Q(visibility=Pin.VISIBILITY_PUBLIC, author__profile__private_profile=False)
            | Q(author=self.request.user)
            | Q(visibility=Pin.VISIBILITY_FOLLOWERS, author__profile__followers=my_profile)
            | Q(author__profile__private_profile=True, author__profile__followers=my_profile)
        )
        core = visibility_q & story_q & (sched | Q(author=self.request.user))
        if apply_story_placement:
            core &= placement_q
        queryset = queryset.filter(core).distinct()
        queryset = queryset.filter(sensitive_pins_query_filter(self.request))
        queryset = queryset.exclude(moderation_hidden=True)
        queryset = filter_pins_exclude_blocked(queryset, self.request)
        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                _viewer_has_reported_pin=Exists(
                    ContentReport.objects.filter(
                        reporter_id=self.request.user.id,
                        pin_id=OuterRef('pk'),
                    )
                )
            )
        if saved_by_me:
            user = self.request.user
            queryset = queryset.filter(id__in=Save.objects.filter(user=user).values('pin_id'))
            saved_at_sub = (
                Save.objects.filter(pin_id=OuterRef('pk'), user=user)
                .order_by('-created_at')
                .values('created_at')[:1]
            )
            queryset = queryset.annotate(_saved_at=Subquery(saved_at_sub)).order_by('-_saved_at')
        return exclude_ephemeral_story_only(queryset)

    def perform_create(self, serializer):
        pin = serializer.save(author=self.request.user)
        pin.refresh_story_expiry()
        pin.save(update_fields=['story_expires_at'])
        update_pin_ai_metadata(pin)

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id:
            raise PermissionDenied('Only the pin author can edit this pin.')
        pin = serializer.save()
        pin.refresh_story_expiry()
        pin.save(update_fields=['story_expires_at'])
        update_pin_ai_metadata(pin)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id:
            raise PermissionDenied('Only the pin author can delete this pin.')
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='save')
    def toggle_save(self, request, slug=None):
        pin = self.get_object()
        save, created = Save.objects.get_or_create(user=request.user, pin=pin)

        if not created:
            save.delete()
            UserInteraction.objects.create(
                user=request.user,
                pin=pin,
                creator=pin.author,
                event_type=UserInteraction.TYPE_SAVE,
                metadata={'action': 'unsave'},
            )
            update_user_embedding(request.user)
            return Response({'status': 'unsaved', 'saves_count': pin.saves_count})

        if pin.author != request.user and pin.author.profile.notifications_saves:
            create_localized_notification(
                recipient=pin.author,
                sender=request.user,
                notification_type='save',
                message_fr=f"{request.user.username} a enregistré votre pin : {pin.title}",
                pin_id=pin.id,
                pin_slug=pin.slug,
                metadata={'is_story': pin.is_story},
            )
        UserInteraction.objects.create(
            user=request.user,
            pin=pin,
            creator=pin.author,
            event_type=UserInteraction.TYPE_SAVE,
            metadata={'action': 'save'},
        )
        update_user_embedding(request.user)

        return Response({'status': 'saved', 'saves_count': pin.saves_count})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, slug=None):
        pin = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, pin=pin)

        if not created:
            like.delete()
            UserInteraction.objects.create(
                user=request.user,
                pin=pin,
                creator=pin.author,
                event_type=UserInteraction.TYPE_LIKE,
                metadata={'action': 'unlike'},
            )
            update_user_embedding(request.user)
            return Response({'status': 'unliked', 'likes_count': pin.likes_count})

        if pin.author != request.user and not pin.is_story:
            create_localized_notification(
                recipient=pin.author,
                sender=request.user,
                notification_type='like',
                message_fr=f"{request.user.username} a aimé votre pin : {pin.title}",
                pin_id=pin.id,
                pin_slug=pin.slug,
            )
        UserInteraction.objects.create(
            user=request.user,
            pin=pin,
            creator=pin.author,
            event_type=UserInteraction.TYPE_LIKE,
            metadata={'action': 'like'},
        )
        update_user_embedding(request.user)

        return Response({'status': 'liked', 'likes_count': pin.likes_count})

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='likes',
    )
    def likers(self, request, slug=None):
        """Liste des comptes ayant liké — réservé à l'auteur du pin."""
        pin = self.get_object()
        if request.user.id != pin.author_id:
            raise PermissionDenied('Only the pin author can see likes.')
        qs = (
            Like.objects.filter(pin_id=pin.id)
            .select_related('user', 'user__profile')
            .order_by('-created_at')[:150]
        )
        likers = []
        for lk in qs:
            user = lk.user
            profile = getattr(user, 'profile', None)
            av = getattr(profile, 'avatar', None) if profile else None
            avatar_url = ''
            if av and getattr(av, 'name', '') and request:
                avatar_url = build_versioned_media_url(request, av)
            likers.append(
                {
                    'username': user.username,
                    'display_name': (
                        ((profile.display_name or user.username).strip()) if profile else user.username
                    ),
                    'avatar_url': avatar_url,
                    'avatar_color': getattr(profile, 'avatar_color', None) or 'bg-neutral-400',
                    'liked_at': lk.created_at.isoformat(),
                }
            )
        return Response({'count': pin.likes_count, 'likers': likers})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='view')
    def view_event(self, request, slug=None):
        pin = self.get_object()
        try:
            dwell_seconds = int(request.data.get('dwell_seconds') or 0)
        except (TypeError, ValueError):
            dwell_seconds = 0
        PinViewEvent.objects.create(user=request.user, pin=pin)
        UserInteraction.objects.create(
            user=request.user,
            pin=pin,
            creator=pin.author,
            event_type=UserInteraction.TYPE_VIEW,
            dwell_seconds=max(0, dwell_seconds),
            metadata={'source': request.data.get('source') or ''},
        )
        update_user_embedding(request.user)
        return Response({'status': 'recorded'})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='search-interactions')
    def search_interactions(self, request):
        query = (request.data.get('query') or '').strip()
        if len(query) < 2:
            return Response({'status': 'ignored'})
        SearchInteraction.objects.create(user=request.user, query=query[:120])
        return Response({'status': 'recorded'})

    def _story_ring_groups_from_pins(self, ordered_pins, request):
        """ordered_pins : ordre reco/global ; couverture = pin la plus récente ; lecture chronologique ancienne → récente."""
        by_author = OrderedDict()
        first_rank = {}
        for rank, pin in enumerate(ordered_pins):
            aid = pin.author_id
            if aid not in by_author:
                by_author[aid] = []
                first_rank[aid] = rank
            by_author[aid].append(pin)

        ordered_aids = sorted(by_author.keys(), key=lambda x: first_rank[x])
        groups = []
        for aid in ordered_aids:
            plist = by_author[aid]
            chron = sorted(plist, key=lambda p: p.created_at)
            cover = max(plist, key=lambda p: p.created_at)
            author = chron[0].author
            profile = author.profile
            avatar_url = ''
            av = getattr(profile, 'avatar', None)
            if av and getattr(av, 'name', ''):
                avatar_url = build_versioned_media_url(request, av)
            cover_url = ''
            if cover.image and getattr(cover.image, 'name', ''):
                cover_url = build_versioned_media_url(request, cover.image)
            elif getattr(cover, 'story_video', None) and cover.story_video and getattr(
                cover.story_video, 'name', ''
            ):
                cover_url = build_versioned_media_url(request, cover.story_video)
            groups.append({
                'username': author.username,
                'display_name': profile.display_name or author.username,
                'avatar_url': avatar_url,
                'avatar_color': profile.avatar_color or 'bg-neutral-400',
                'cover_image_url': cover_url,
                'pins': PinSerializer(chron, many=True, context={'request': request}).data,
            })
        return groups

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='active-stories')
    def active_stories(self, request):
        username = (request.query_params.get('username') or '').strip()
        sched_ok = self._scheduled_publish_ok_q()
        qs = (
            Pin.objects.filter(is_story=True)
            .filter(sched_ok)
            .exclude(story_expires_at__isnull=True)
            .exclude(story_expires_at__lte=timezone.now())
            .select_related('author', 'author__profile', 'topic')
            .prefetch_related('hashtags', 'boards', 'variant_assets')
        )

        if username:
            owner = User.objects.filter(username=username).first()
            if not owner:
                return Response({'pins': [], 'groups': []})
            qs = qs.filter(author=owner).order_by('media_sensitive_blur', '-created_at')[:48]
            visible = [pin for pin in qs if pin_is_visible_for_request(pin, request)]
            visible = sorted(visible, key=lambda p: p.created_at)
            serializer = PinSerializer(visible, many=True, context={'request': request})
            return Response({'pins': serializer.data, 'groups': []})
        pool = list(qs.order_by('media_sensitive_blur', '-created_at')[:150])
        visible = [pin for pin in pool if pin_is_visible_for_request(pin, request)]
        user = request.user
        if (
            user.is_authenticated
            and getattr(user.profile, 'notifications_recommendations', False)
            and visible
        ):
            topic_scores = self._build_topic_scores(user)
            if topic_scores:
                vis_qs = Pin.objects.filter(id__in=[p.id for p in visible]).select_related(
                    'author',
                    'author__profile',
                    'topic',
                )
                visible = self._ordered_by_topic_score(vis_qs, topic_scores)
        visible = visible[:80]
        groups = self._story_ring_groups_from_pins(visible, request)
        return Response({'pins': [], 'groups': groups})

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='standalone-story',
    )
    def standalone_story(self, request):
        """
        Story Plus/Pro hors flux « pin » classique : image + légende (pas de vidéo).
        `story_ephemeral` : purge DB + fichiers après `story_expires_at` (voir management command).
        """
        _enforce_subscription_state(request.user.profile)
        request.user.profile.refresh_from_db()
        prof = request.user.profile
        if prof.subscription_plan not in {Profile.PLAN_PLUS, Profile.PLAN_PRO}:
            return Response(
                {'error': 'Story éphémère réservée aux abonnements Plus et Pro.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = StandaloneStoryCreateSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        validated = ser.validated_data
        title_base = f'Story · {timezone.now().strftime("%d/%m/%Y %H:%M")}'
        try:
            validate_pin_text(title_base, validated.get('description', '') or '', [], [])
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        apply_pin_creation_rate_limits(request.user.id, True)
        enforce_identical_content_flood(
            request.user.id,
            'pin',
            pin_body_fingerprint(title_base, validated.get('description', '') or ''),
        )

        pin = Pin(
            author=request.user,
            title=title_base,
            description=validated.get('description', '') or '',
            link='',
            visibility=Pin.VISIBILITY_PUBLIC,
            is_story=True,
            story_ephemeral=True,
            topic=None,
            media_sensitive_blur=validated.get('media_sensitive_blur', False),
        )
        if validated.get('image'):
            pin.image = validated['image']
        pin.save()
        pin.refresh_story_expiry()
        pin.save(update_fields=['story_expires_at'])
        return Response(PinSerializer(pin, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, slug=None):
        pin = self.get_object()

        if request.method == 'POST':
            if not request.user.is_authenticated:
                return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            if not user_can_comment_on_pin(pin, request.user):
                return Response(
                    {'error': 'Comments are closed or restricted on this pin'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            text = sanitize_comment_plain_text((request.data.get('text', '') or '').strip())
            gif_url = request.data.get('gif')
            media_file = request.FILES.get('media')
            parent_id = request.data.get('parentId') or request.data.get('parent')
            try:
                validate_comment_text(text)
                apply_comment_rate_limit(request.user.id, client_ip_from_request(request))
                gif_key = gif_url if isinstance(gif_url, str) else ''
                enforce_identical_content_flood(
                    request.user.id,
                    'comment',
                    comment_body_fingerprint(text, gif_key),
                )
            except serializers.ValidationError as exc:
                detail = exc.detail
                if isinstance(detail, dict):
                    body = detail
                elif isinstance(detail, list):
                    body = {'non_field_errors': detail}
                else:
                    body = {'non_field_errors': [str(detail)]}
                return Response(body, status=status.HTTP_400_BAD_REQUEST)
            if not text and not gif_url and not media_file:
                return Response({'error': 'Comment text, gif or media is required'}, status=status.HTTP_400_BAD_REQUEST)
            if gif_url and not request.user.profile.can_use_comment_gifs:
                return Response(
                    {'error': 'GIF links in comments require Plus or Pro plan'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if media_file:
                if not request.user.profile.can_use_comment_gifs:
                    return Response(
                        {'error': 'Images and GIFs in comments require Plus or Pro plan'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                if not str(getattr(media_file, 'content_type', '')).startswith('image/'):
                    return Response({'error': 'Only image files are allowed'}, status=status.HTTP_400_BAD_REQUEST)
                if media_file.size > 5 * 1024 * 1024:
                    return Response({'error': 'Media file must be <= 5MB'}, status=status.HTTP_400_BAD_REQUEST)
                media_file = compress_comment_media_upload(media_file)
                if getattr(media_file, 'size', 0) > 5 * 1024 * 1024:
                    return Response({'error': 'Media file must be <= 5MB'}, status=status.HTTP_400_BAD_REQUEST)
            parent = None
            if parent_id:
                try:
                    parent = Comment.objects.get(id=parent_id, pin=pin)
                except Comment.DoesNotExist:
                    return Response({'error': 'Parent comment not found'}, status=status.HTTP_404_NOT_FOUND)
            comment = Comment.objects.create(
                user=request.user,
                pin=pin,
                text=text,
                gif_url=gif_url,
                media=media_file,
                parent=parent,
                original_language=detect_original_language(text) if text else 'auto',
            )
            tags = extract_hashtags(text)
            if tags:
                hashtag_objs = []
                for tag in tags:
                    hashtag, _ = Hashtag.objects.get_or_create(name=tag)
                    hashtag_objs.append(hashtag)
                comment.hashtags.set(hashtag_objs)
            mentions = sorted(set(re.findall(r'@([A-Za-z0-9_\.]{2,80})', text or '')))
            if mentions:
                comment.mentions = mentions
                comment.save(update_fields=['mentions'])
                mentioned_users = User.objects.filter(username__in=mentions)
                for mentioned_user in mentioned_users:
                    if mentioned_user != request.user:
                        create_localized_notification(
                            recipient=mentioned_user,
                            sender=request.user,
                            notification_type='comment',
                            message_fr=f"{request.user.username} vous a mentionné dans un commentaire.",
                            pin_id=pin.id,
                            pin_slug=pin.slug,
                            comment_id=comment.id,
                            metadata={'is_story': pin.is_story},
                        )

            if parent and parent.user != request.user:
                create_localized_notification(
                    recipient=parent.user,
                    sender=request.user,
                    notification_type='comment',
                    message_fr=f"{request.user.username} a répondu à votre commentaire sur {pin.title}.",
                    pin_id=pin.id,
                    pin_slug=pin.slug,
                    comment_id=comment.id,
                    metadata={'is_story': pin.is_story},
                )

            if pin.author != request.user and not (parent and parent.user == pin.author):
                create_localized_notification(
                    recipient=pin.author,
                    sender=request.user,
                    notification_type='comment',
                    message_fr=f"{request.user.username} a commenté votre pin : {pin.title}",
                    pin_id=pin.id,
                    pin_slug=pin.slug,
                    comment_id=comment.id,
                    metadata={'is_story': pin.is_story},
                )

            serializer = CommentSerializer(comment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        sort = (request.query_params.get('sort') or 'recent').lower()
        highlight_raw = (request.query_params.get('highlight_comment_id') or '').strip()
        highlighted_comment_id = int(highlight_raw) if highlight_raw.isdigit() else None
        highlighted_parent_id = None
        if highlighted_comment_id:
            highlighted_comment = Comment.objects.filter(id=highlighted_comment_id, pin=pin).select_related('parent').first()
            if highlighted_comment:
                highlighted_parent_id = highlighted_comment.parent_id or highlighted_comment.id

        comments = (
            pin.comments.filter(parent__isnull=True)
            .select_related('pin', 'user', 'user__profile')
            .prefetch_related('replies', 'replies__user', 'replies__user__profile', 'hashtags')
        )
        if request.user.is_authenticated:
            comments = comments.annotate(
                _viewer_has_reported_comment=Exists(
                    ContentReport.objects.filter(
                        reporter=request.user,
                        comment_id=OuterRef('pk'),
                    )
                )
            )
        if sort == 'relevant':
            comments = comments.annotate(likes_total=Count('comment_likes')).order_by('-likes_total', '-created_at')
        else:
            comments = comments.order_by('-created_at')
        if highlighted_parent_id:
            comments = comments.annotate(
                highlight_priority=Case(
                    When(id=highlighted_parent_id, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by('highlight_priority', *comments.query.order_by)
        paginator = CommentPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentSerializer(
            page,
            many=True,
            context={
                'request': request,
                'include_replies': True,
                'replies_page_size': int(request.query_params.get('replies_page_size', 3) or 3),
                'replies_sort': sort,
                'highlighted_comment_id': highlighted_comment_id,
            },
        )
        return paginator.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated],
        url_path=r'comments/(?P<comment_id>\d+)/moderate',
    )
    def moderate_comment(self, request, slug=None, comment_id=None):
        pin = self.get_object()
        if pin.author_id != request.user.id:
            return Response(
                {'error': 'Only the pin owner can moderate comments'},
                status=status.HTTP_403_FORBIDDEN,
            )
        comment = Comment.objects.filter(id=comment_id, pin=pin).first()
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        hidden = request.data.get('hidden')
        if hidden is True:
            comment.hidden_by_owner = True
        elif hidden is False:
            comment.hidden_by_owner = False
        else:
            return Response(
                {'error': 'Provide hidden as true or false'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comment.save(update_fields=['hidden_by_owner'])
        serializer = CommentSerializer(
            comment,
            context={'request': request, 'include_replies': False},
        )
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['delete'],
        permission_classes=[permissions.IsAuthenticated],
        url_path=r'comments/(?P<comment_id>\d+)',
    )
    def delete_comment(self, request, slug=None, comment_id=None):
        pin = self.get_object()
        comment = Comment.objects.filter(id=comment_id, pin=pin).first()
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.id != comment.user_id and pin.author_id != request.user.id:
            return Response(
                {'error': 'Only the comment author or the pin owner can delete this comment'},
                status=status.HTTP_403_FORBIDDEN,
            )
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='report')
    def report_pin(self, request, slug=None):
        pin = self.get_object()
        if pin.author_id == request.user.id:
            return Response({'error': 'Cannot report your own content'}, status=status.HTTP_400_BAD_REQUEST)
        if ContentReport.objects.filter(reporter=request.user, pin=pin).exists():
            return Response(
                {'error': 'already_reported', 'report_count': pin.report_count},
                status=status.HTTP_409_CONFLICT,
            )
        parsed = _parse_report_request(request)
        if parsed is None:
            return Response(
                {'details': ['Merci d’ajouter une brève description (10 caractères minimum).']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category, details = parsed
        reason_preview = details[:500]
        try:
            ContentReport.objects.create(
                reporter=request.user,
                pin=pin,
                category=category,
                details=details,
                reason=reason_preview,
            )
        except IntegrityError:
            return Response(
                {'error': 'already_reported', 'report_count': pin.report_count},
                status=status.HTTP_409_CONFLICT,
            )
        increment_pin_reports(pin.id)
        pin.refresh_from_db()
        apply_pin_report_thresholds(pin)
        pin.refresh_from_db()
        return Response({
            'status': 'ok',
            'report_count': pin.report_count,
            'needs_review': pin.needs_review,
            'moderation_hidden': pin.moderation_hidden,
        })

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated],
        url_path=r'comments/(?P<comment_id>\d+)/report',
    )
    def report_comment(self, request, comment_id=None):
        comment = Comment.objects.select_related('pin').filter(id=comment_id).first()
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if not self.get_queryset().filter(id=comment.pin_id).exists():
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if comment.user_id == request.user.id:
            return Response({'error': 'Cannot report your own comment'}, status=status.HTTP_400_BAD_REQUEST)
        if ContentReport.objects.filter(reporter=request.user, comment=comment).exists():
            return Response(
                {'error': 'already_reported', 'report_count': comment.report_count},
                status=status.HTTP_409_CONFLICT,
            )
        parsed = _parse_report_request(request)
        if parsed is None:
            return Response(
                {'details': ['Merci d’ajouter une brève description (10 caractères minimum).']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category, details = parsed
        reason_preview = details[:500]
        try:
            ContentReport.objects.create(
                reporter=request.user,
                comment=comment,
                category=category,
                details=details,
                reason=reason_preview,
            )
        except IntegrityError:
            return Response(
                {'error': 'already_reported', 'report_count': comment.report_count},
                status=status.HTTP_409_CONFLICT,
            )
        increment_comment_reports(comment.id)
        comment.refresh_from_db()
        apply_comment_report_thresholds(comment)
        comment.refresh_from_db()
        return Response({
            'status': 'ok',
            'report_count': comment.report_count,
            'needs_review': comment.needs_review,
            'moderation_hidden': comment.moderation_hidden,
        })

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[permissions.IsAuthenticatedOrReadOnly],
        url_path='comments/(?P<comment_id>[^/.]+)/replies',
    )
    def comment_replies(self, request, comment_id=None):
        try:
            parent_comment = Comment.objects.select_related('pin').get(id=comment_id)
        except Comment.DoesNotExist:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Respect pin visibility when loading replies.
        pin = parent_comment.pin
        if not self.get_queryset().filter(id=pin.id).exists():
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

        replies = (
            parent_comment.replies.all()
            .select_related('pin', 'user', 'user__profile')
            .prefetch_related('hashtags')
        )
        sort = (request.query_params.get('sort') or 'recent').lower()
        if sort == 'relevant':
            replies = replies.annotate(likes_total=Count('comment_likes')).order_by('-likes_total', '-created_at')
        else:
            replies = replies.order_by('-created_at')

        highlight_raw = (request.query_params.get('highlight_comment_id') or '').strip()
        highlighted_comment_id = int(highlight_raw) if highlight_raw.isdigit() else None
        if highlighted_comment_id:
            replies = replies.annotate(
                highlight_priority=Case(
                    When(id=highlighted_comment_id, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by('highlight_priority', *replies.query.order_by)
        paginator = ReplyPagination()
        page = paginator.paginate_queryset(replies, request)
        serializer = CommentSerializer(
            page,
            many=True,
            context={'request': request, 'include_replies': False},
        )
        return paginator.get_paginated_response(serializer.data)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='comments/(?P<comment_id>[^/.]+)/like',
    )
    def like_comment(self, request, comment_id=None):
        try:
            comment = Comment.objects.select_related('pin', 'user').get(id=comment_id)
        except Comment.DoesNotExist:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Respect pin visibility permissions.
        if not self.get_queryset().filter(id=comment.pin_id).exists():
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

        like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
        if not created:
            like.delete()
            return Response({'status': 'unliked', 'likes_count': comment.comment_likes.count()})

        if comment.user != request.user:
            create_localized_notification(
                recipient=comment.user,
                sender=request.user,
                notification_type='like',
                message_fr=f"{request.user.username} a aimé votre commentaire.",
                pin_id=comment.pin_id,
                pin_slug=comment.pin.slug,
                comment_id=comment.id,
                metadata={'is_story': comment.pin.is_story},
            )

        return Response({'status': 'liked', 'likes_count': comment.comment_likes.count()})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def recommendations(self, request):
        base_queryset = self.get_queryset().exclude(author=request.user)
        recommendations = rank_recommendations_for_user(request.user, base_queryset)
        page = self.paginate_queryset(recommendations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(recommendations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def following(self, request):
        following_profiles = request.user.profile.following.all()
        following_users = [p.user for p in following_profiles]
        queryset = (
            self.get_queryset()
            .filter(author__in=following_users)
            .exclude(author=request.user)
            .order_by('media_sensitive_blur', '-created_at')
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='discover')
    def discover(self, request):
        queryset = self.get_queryset()
        if request.user.is_authenticated:
            following_profiles = request.user.profile.following.all()
            queryset = queryset.exclude(author__profile__in=following_profiles).exclude(author=request.user)
        topic = (request.query_params.get('topic') or '').strip()
        queryset = self._apply_topic_filter(queryset, topic)
        q_disc = (request.query_params.get('q') or '').strip()
        if q_disc:
            queryset = queryset.filter(broad_pin_q(q_disc))
        page = self.paginate_queryset(queryset.order_by('media_sensitive_blur', '-created_at'))
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='header-search')
    def header_search(self, request):
        """Pins + profils (recherche floue) et branche « pour vous » (recommandations) pour le bandeau."""
        limit_raw = (request.query_params.get('limit') or '8').strip()
        try:
            lim = max(1, min(int(limit_raw), 20))
        except ValueError:
            lim = 8
        pin_limit = lim
        user_limit = min(10, lim + 2)
        rec_limit = min(8, lim)
        board_limit = min(10, lim + 2)

        q = (request.query_params.get('q') or '').strip()
        base_pins = self.get_queryset()
        if request.user.is_authenticated:
            base_pins = base_pins.exclude(author=request.user)

        ctx = {'request': request}
        pin_ids_in_results: set[int] = set()

        pins_data = []
        if len(q) >= 1:
            candidates = list(base_pins.filter(broad_pin_q(q))[:150])
            candidates.sort(
                key=lambda p: -fuzzy_score(
                    q,
                    p.title or '',
                    p.description or '',
                    p.author.username,
                )
            )
            pins_trim = candidates[:pin_limit]
            pin_ids_in_results = {p.id for p in pins_trim}
            pins_data = self.get_serializer(pins_trim, many=True, context=ctx).data

        users_data = []
        if len(q) >= 1:
            users_qs = (
                User.objects.select_related('profile')
                .filter(profile__discoverable_profile=True)
                .filter(Q(username__icontains=q) | Q(profile__display_name__icontains=q))
            )
            viewer = request.user if request.user.is_authenticated else None
            if viewer and viewer.is_authenticated:
                users_qs = users_qs.exclude(pk=viewer.pk)
                forb = blocked_mutual_user_ids(viewer)
                if forb:
                    users_qs = users_qs.exclude(pk__in=forb)
            ul = list(users_qs[:80])
            ul.sort(
                key=lambda u: -fuzzy_score(
                    q,
                    u.username,
                    (u.profile.display_name or '') if getattr(u, 'profile', None) else '',
                )
            )
            for u in ul[:user_limit]:
                prof = u.profile
                users_data.append(
                    {
                        'username': u.username,
                        'display_name': (prof.display_name or u.username).strip() or u.username,
                        'avatar_color': prof.avatar_color or 'bg-neutral-400',
                        'avatar': build_versioned_media_url(request, prof.avatar)
                        if prof.avatar and getattr(prof.avatar, 'name', '')
                        else None,
                    }
                )

        boards_qs = Board.objects.select_related('user').prefetch_related('collaborators')
        if request.user.is_authenticated:
            boards_qs = boards_qs.filter(
                Q(is_private=False) | Q(user=request.user) | Q(collaborators=request.user)
            )
        else:
            boards_qs = boards_qs.filter(is_private=False)
        if q:
            boards_qs = boards_qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q) | Q(user__username__icontains=q)
            ).distinct()
            board_candidates = list(boards_qs[:80])
            board_candidates.sort(
                key=lambda b: -fuzzy_score(
                    q,
                    b.name or '',
                    b.description or '',
                    b.user.username if getattr(b, 'user', None) else '',
                )
            )
        else:
            board_candidates = list(
                boards_qs.annotate(pins_total=Count('pins')).order_by('-pins_total', '-created_at')[:board_limit]
            )
        boards_data = []
        for b in board_candidates[:board_limit]:
            payload = BoardSerializer(b, context=ctx).data
            previews = payload.get('preview_images') or []
            payload['cover_image_url'] = previews[0] if previews else ''
            boards_data.append(payload)

        rec_data = []
        if request.user.is_authenticated:
            rec_base = self.get_queryset().exclude(author=request.user)
            topic_scores = self._build_topic_scores(request.user)
            ranked = self._ordered_by_topic_score(rec_base, topic_scores)
            picked = []
            for p in ranked:
                if p.id in pin_ids_in_results:
                    continue
                if q:
                    if fuzzy_score(q, p.title or '', p.description or '', p.author.username) < 0.22:
                        continue
                picked.append(p)
                if len(picked) >= rec_limit:
                    break
            rec_data = self.get_serializer(picked, many=True, context=ctx).data

        return Response(
            {
                'pins': pins_data,
                'users': users_data,
                'boards': boards_data,
                'recommended_pins': rec_data,
                'query': q,
            }
        )

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='explore-boards')
    def explore_boards(self, request):
        """Tableaux publics (découverte) paginés — même filtres que le bandeau header-search."""
        page_raw = (request.query_params.get('page') or '1').strip()
        ps_raw = (request.query_params.get('page_size') or '24').strip()
        try:
            page = max(1, int(page_raw))
        except ValueError:
            page = 1
        try:
            page_size = max(1, min(int(ps_raw), 48))
        except ValueError:
            page_size = 24

        q = (request.query_params.get('q') or '').strip()
        boards_qs = Board.objects.select_related('user').prefetch_related('collaborators')
        if request.user.is_authenticated:
            boards_qs = boards_qs.filter(
                Q(is_private=False) | Q(user=request.user) | Q(collaborators=request.user)
            ).distinct()
        else:
            boards_qs = boards_qs.filter(is_private=False)
        if q:
            boards_qs = boards_qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q) | Q(user__username__icontains=q)
            ).distinct()
            board_candidates = list(boards_qs[:400])
            board_candidates.sort(
                key=lambda b: -fuzzy_score(
                    q,
                    b.name or '',
                    b.description or '',
                    b.user.username if getattr(b, 'user', None) else '',
                )
            )
            ordered_ids = [b.id for b in board_candidates]
            order = Case(
                *[When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ordered_ids)],
                output_field=IntegerField(),
            )
            qs = Board.objects.filter(pk__in=ordered_ids).select_related('user').prefetch_related('collaborators')
            qs = qs.annotate(_sort_order=order).order_by('_sort_order', '-created_at')
        else:
            qs = (
                boards_qs.annotate(pins_total=Count('pins'))
                .order_by('-pins_total', '-created_at')
            )

        total = qs.count()
        start = (page - 1) * page_size
        chunk = list(qs[start : start + page_size])

        ctx = {'request': request}
        boards_data = []
        for b in chunk:
            payload = BoardSerializer(b, context=ctx).data
            previews = payload.get('preview_images') or []
            payload['cover_image_url'] = previews[0] if previews else ''
            boards_data.append(payload)

        def _page_url(p: int):
            qd = {'page': p, 'page_size': page_size}
            if q:
                qd['q'] = q
            return request.build_absolute_uri(f"{request.path}?{urlencode(qd)}")

        next_url = _page_url(page + 1) if start + page_size < total else None
        previous_url = _page_url(page - 1) if page > 1 else None

        return Response(
            {
                'count': total,
                'next': next_url,
                'previous': previous_url,
                'results': boards_data,
            }
        )

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='home-feed')
    def home_feed(self, request):
        topic = (request.query_params.get('topic') or '').strip()
        following_profiles = request.user.profile.following.all()
        following_queryset = (
            self.get_queryset()
            .filter(author__profile__in=following_profiles)
            .exclude(author=request.user)
        )
        discover_queryset = (
            self.get_queryset()
            .exclude(author__profile__in=following_profiles)
            .exclude(author=request.user)
        )
        if topic:
            following_queryset = self._apply_topic_filter(following_queryset, topic)
            discover_queryset = self._apply_topic_filter(discover_queryset, topic)

        topic_scores = self._build_topic_scores(request.user)
        following_items = list(
            following_queryset.order_by('media_sensitive_blur', '-created_at')[:FEED_INTERLEAVE_SOURCE_CAP]
        )
        discover_items = self._ordered_by_topic_score(
            discover_queryset, topic_scores, cap=FEED_INTERLEAVE_SOURCE_CAP
        )

        mixed = []
        follow_idx = 0
        discover_idx = 0
        while follow_idx < len(following_items) or discover_idx < len(discover_items):
            if follow_idx < len(following_items):
                mixed.append(following_items[follow_idx])
                follow_idx += 1
            if discover_idx < len(discover_items):
                mixed.append(discover_items[discover_idx])
                discover_idx += 1
        if not following_items:
            mixed = discover_items

        # Correction : Pagination directe sur le QuerySet ou la liste
        page = self.paginate_queryset(mixed)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Fallback (si pagination désactivée ou échouée sur la liste)
        serializer = self.get_serializer(mixed, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def topics(self, request):
        limit_raw = (request.query_params.get('limit') or '10').strip()
        limit = int(limit_raw) if limit_raw.isdigit() else 10
        limit = max(1, min(limit, 30))
        search_query = (request.query_params.get('q') or '').strip()
        search_query_lower = search_query.lower()

        now = timezone.now()
        schedule_public = Q(scheduled_publish_at__isnull=True) | Q(scheduled_publish_at__lte=now)
        story_public = (
            Q(is_story=False)
            | Q(is_story=True, story_ephemeral=False)
            | Q(is_story=True, story_ephemeral=True, story_expires_at__gt=now)
        )

        base_qs = (
            Pin.objects.exclude(topic__isnull=True)
            .exclude(visibility=Pin.VISIBILITY_PRIVATE)
            .filter(schedule_public)
            .filter(story_public)
        )
        topic_pin_filter = (
            ~Q(pins__visibility=Pin.VISIBILITY_PRIVATE)
            & (
                Q(pins__scheduled_publish_at__isnull=True)
                | Q(pins__scheduled_publish_at__lte=now)
            )
            & (
                Q(pins__is_story=False)
                | Q(pins__is_story=True, pins__story_ephemeral=False)
                | Q(
                    pins__is_story=True,
                    pins__story_ephemeral=True,
                    pins__story_expires_at__gt=now,
                )
            )
        )
        if not viewer_is_verified_adult(request):
            topic_pin_filter &= Q(pins__media_sensitive_blur=False)
        topics_qs = (
            Topic.objects.filter(is_active=True)
            .annotate(
                pin_count=Count(
                    'pins',
                    filter=topic_pin_filter,
                    distinct=True,
                )
            )
            .filter(pin_count__gt=0)
            .order_by('-pin_count', 'name')
            .values('id', 'name', 'slug', 'icon', 'color', 'cover_image', 'pin_count')
        )

        # Suggestions personnalisées pour l'utilisateur connecté.
        if request.user.is_authenticated:
            suggested_topics = (
                base_qs.filter(
                    Q(likes__user=request.user)
                    | Q(saves__user=request.user)
                    | Q(comments__user=request.user)
                )
                .values('topic_id')
                .annotate(interactions=Count('id'))
                .order_by('-interactions', 'topic_id')
            )
            suggested_ids = [row['topic_id'] for row in suggested_topics[: (200 if search_query else limit)] if row['topic_id']]
            if suggested_ids:
                # Garder les suggestions d'abord, puis compléter par les plus populaires.
                popular_rows = list(topics_qs)
                topic_map = {row['id']: row for row in popular_rows}
                merged = [topic_map[topic_id] for topic_id in suggested_ids if topic_id in topic_map]
                for row in popular_rows:
                    if len(merged) >= (200 if search_query else limit):
                        break
                    if row['id'] not in suggested_ids:
                        merged.append(row)
                topics_qs = merged[: (200 if search_query else limit)]
            else:
                topics_qs = list(topics_qs[: (200 if search_query else limit)])
        else:
            topics_qs = list(topics_qs[: (200 if search_query else limit)])

        target_lang = resolve_topic_language(request)
        items = []
        translator = Translator() if target_lang != 'fr' else None
        for item in topics_qs:
            topic_name = item['name']
            display_name, translations = ensure_topic_translation(
                topic_name,
                target_lang,
                translator=translator,
            )
            if search_query_lower:
                if not (
                    search_query_lower in topic_name.lower()
                    or search_query_lower in display_name.lower()
                    or any(search_query_lower in str(value).lower() for value in translations.values())
                ):
                    continue
            cover_rel = item.get('cover_image') or ''
            cover_image_url = None
            if cover_rel:
                try:
                    base = request.build_absolute_uri(default_storage.url(cover_rel))
                    cover_image_url = append_version_using_media_path(
                        base, relative_under_media=cover_rel
                    )
                except Exception:
                    cover_image_url = None
            items.append({
                'name': display_name,
                'originalName': topic_name,
                'slug': item['slug'],
                'icon': item['icon'],
                'color': item['color'],
                'coverImage': cover_image_url,
                'pinCount': item['pin_count'],
                'translations': translations,
            })
        if search_query_lower:
            items = items[:limit]
        return Response(items)

    @action(detail=True, methods=['get', 'post', 'delete'], permission_classes=[permissions.IsAuthenticated], url_path='private-tags')
    def private_tags(self, request, slug=None):
        pin = self.get_object()
        if pin.author != request.user:
            return Response({'error': 'Only pin owner can manage private tags'}, status=status.HTTP_403_FORBIDDEN)
        if request.method in ['POST', 'DELETE'] and not request.user.profile.can_use_private_tags:
            return Response(
                {'error': 'Private tags require Plus or Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.method == 'GET':
            tags = list(
                PrivatePinTag.objects.filter(user=request.user, pin=pin)
                .values_list('tag', flat=True)
                .order_by('tag')
            )
            return Response({'tags': tags})
        if request.method == 'POST':
            raw_tags = request.data.get('tags', [])
            if isinstance(raw_tags, str):
                raw_tags = [t.strip() for t in raw_tags.split(',')]
            for tag in raw_tags:
                cleaned = str(tag).strip()
                if cleaned:
                    PrivatePinTag.objects.get_or_create(user=request.user, pin=pin, tag=cleaned)
            tags = list(
                PrivatePinTag.objects.filter(user=request.user, pin=pin)
                .values_list('tag', flat=True)
                .order_by('tag')
            )
            return Response({'tags': tags}, status=status.HTTP_201_CREATED)
        tag = (request.data.get('tag') or '').strip()
        if not tag:
            return Response({'error': 'tag is required'}, status=status.HTTP_400_BAD_REQUEST)
        PrivatePinTag.objects.filter(user=request.user, pin=pin, tag=tag).delete()
        tags = list(
            PrivatePinTag.objects.filter(user=request.user, pin=pin)
            .values_list('tag', flat=True)
            .order_by('tag')
        )
        return Response({'tags': tags})

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='download')
    def download(self, request, slug=None):
        pin = self.get_object()
        profile = request.user.profile
        if not profile.can_download:
            return Response(
                {'error': 'Download requires Plus or Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        requested_quality = (request.query_params.get('quality') or 'standard').strip().lower()
        allowed_qualities = {'standard'}
        if profile.subscription_plan == profile.PLAN_PRO:
            allowed_qualities.update({'hd', '4k'})
        if requested_quality not in allowed_qualities:
            return Response(
                {'error': f'Quality "{requested_quality}" not allowed for your plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not pin.image:
            return Response(
                {'error': 'This pin has no image to download (video-only stories cannot be exported here).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            apply_wm = profile.subscription_plan in {profile.PLAN_PLUS, profile.PLAN_PRO}
            download_url = _pin_download_absolute_url(
                request, pin, requested_quality, apply_watermark=apply_wm
            )
        except Exception:
            download_url = build_versioned_media_url(request, pin.image)
        return Response({
            'download_url': download_url,
            'quality': requested_quality,
        })

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='creator-stats')
    def creator_stats(self, request):
        profile = request.user.profile
        if profile.subscription_plan != profile.PLAN_PRO:
            return Response(
                {'error': 'Advanced stats require Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        user = request.user
        totals_only = str(request.query_params.get('totals_only') or '').lower() in ('1', 'true', 'yes')
        try:
            top_page = int(request.query_params.get('top_page') or 1)
        except ValueError:
            top_page = 1
        try:
            top_page_size = int(request.query_params.get('top_page_size') or 10)
        except ValueError:
            top_page_size = 10
        top_page = max(1, top_page)

        skip_cache = str(request.query_params.get('no_cache') or '').lower() in ('1', 'true', 'yes')
        cache_key = f'pinova:creator_stats:v1:{user.id}:{totals_only}:{top_page}:{top_page_size}'
        if not skip_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        totals = creator_totals_for_user(user)
        if totals_only:
            payload = {
                'totals': totals,
                'top_pins': [],
                'top_pins_pagination': {
                    'page': 1,
                    'page_size': top_page_size,
                    'total_items': 0,
                    'total_pages': 1,
                    'has_next': False,
                    'has_previous': False,
                },
            }
            if not skip_cache:
                cache.set(cache_key, payload, 90)
            return Response(payload)

        top_pins_payload, top_total, t_page, t_psize, t_pages = paginated_creator_top_pins(
            user, page=top_page, page_size=top_page_size
        )
        payload = {
            'totals': totals,
            'top_pins': top_pins_payload,
            'top_pins_pagination': {
                'page': t_page,
                'page_size': t_psize,
                'total_items': top_total,
                'total_pages': t_pages,
                'has_next': t_page < t_pages,
                'has_previous': t_page > 1,
            },
        }
        if not skip_cache:
            cache.set(cache_key, payload, 75)
        return Response(payload)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='creator-weekly-stats')
    def creator_weekly_stats(self, request):
        """Vues des 7 derniers jours (PinViewEvent) pour rétention digest & dashboard Pro."""
        profile = request.user.profile
        if profile.subscription_plan != profile.PLAN_PRO:
            return Response(
                {'error': 'Weekly creator stats require Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            days = int(request.query_params.get('days') or 7)
        except ValueError:
            days = 7
        days = max(1, min(days, 31))
        try:
            wpage = int(request.query_params.get('page') or 1)
        except ValueError:
            wpage = 1
        try:
            wsize = int(request.query_params.get('page_size') or 10)
        except ValueError:
            wsize = 10
        wpage = max(1, wpage)

        skip_cache = str(request.query_params.get('no_cache') or '').lower() in ('1', 'true', 'yes')
        since = timezone.now() - timedelta(days=days)
        wcache_key = f'pinova:creator_weekly:v1:{request.user.id}:{days}:{wsize}:{wpage}'
        if wpage == 1 and not skip_cache:
            hit = cache.get(wcache_key)
            if hit is not None:
                return Response(hit)

        wrows, total_pins_period, total_view_events, w_p, w_ps, w_pages = weekly_creator_pins_page(
            request.user, days=days, page=wpage, page_size=wsize
        )
        period_engagement = creator_period_engagement_totals(request.user, since)
        rows = []
        for row in wrows:
            pin = row['pin']
            thumb = pin_thumbnail_absolute_url(pin, request)
            rows.append({
                'id': pin.id,
                'slug': pin.slug,
                'title': pin.title,
                'views_week': row['views_week'],
                'likes_week': row.get('likes_week', 0),
                'saves_week': row.get('saves_week', 0),
                'comments_week': row.get('comments_week', 0),
                'thumbnail_url': thumb,
            })
        body = {
            'period_days': days,
            'since': since.isoformat(),
            'total_view_events_period': total_view_events,
            'pins_with_views_period': total_pins_period,
            'period_engagement': period_engagement,
            'top_pins': rows,
            'pagination': {
                'page': w_p,
                'page_size': w_ps,
                'total_items': total_pins_period,
                'total_pages': w_pages,
                'has_next': w_p < w_pages,
                'has_previous': w_p > 1,
            },
        }
        if wpage == 1 and not skip_cache:
            cache.set(wcache_key, body, 50)
        return Response(body)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='creator-engagement')
    def creator_engagement(self, request):
        """Acteurs les plus actifs par type d’interaction (likes, saves, comments, views) sur une période."""
        profile = request.user.profile
        if profile.subscription_plan != profile.PLAN_PRO:
            return Response(
                {'error': 'Creator engagement requires Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        action = str(request.query_params.get('action') or '').strip().lower()
        if not action:
            return Response({'error': 'action is required'}, status=status.HTTP_400_BAD_REQUEST)
        if action not in VALID_ACTIONS:
            return Response(
                {'error': 'invalid action', 'allowed': sorted(VALID_ACTIONS)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            days = int(request.query_params.get('days') or 30)
        except ValueError:
            days = 30
        try:
            limit = int(request.query_params.get('limit') or 25)
        except ValueError:
            limit = 25
        skip_cache = str(request.query_params.get('no_cache') or '').lower() in ('1', 'true', 'yes')
        e_key = f'pinova:creator_engagement:v1:{request.user.id}:{action}:{days}:{limit}'
        if not skip_cache:
            hit = cache.get(e_key)
            if hit is not None:
                return Response(hit)
        body = creator_engagement_breakdown(request, request.user, action=action, days=days, limit=limit)
        if not skip_cache:
            cache.set(e_key, body, 45)
        return Response(body)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def provenance(self, request, slug=None):
        self.get_object()
        return Response({'root_hash': '', 'events': []})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='translate-description')
    def translate_description(self, request, slug=None):
        pin = self.get_object()
        target_lang = self._resolve_target_lang(request)
        original_language = detect_original_language(pin.description or '')
        translator = Translator()
        try:
            translated = async_to_sync(translate_text_to)(translator, pin.description or '', target_lang)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            'original': pin.description,
            'original_language': original_language,
            'translated': translated,
            'target_lang': target_lang,
            'translation_source': 'auto',
        })

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='comments/(?P<comment_id>[^/.]+)/translate')
    def translate_comment(self, request, comment_id=None):
        target_lang = self._resolve_target_lang(request)
        try:
            comment = Comment.objects.select_related('pin', 'user').get(id=comment_id)
        except Comment.DoesNotExist:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if not viewer_sees_comment_content(comment, comment.pin, request):
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        original_language = comment.original_language or detect_original_language(comment.text)
        if comment.original_language != original_language:
            comment.original_language = original_language
            comment.save(update_fields=['original_language'])
        translator = Translator()
        try:
            translated = async_to_sync(translate_text_to)(translator, comment.text, target_lang)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            'id': comment.id,
            'original': comment.text,
            'original_language': original_language,
            'translated': translated,
            'target_lang': target_lang,
            'translation_source': 'auto',
        })


class BoardViewSet(viewsets.ModelViewSet):
    serializer_class = BoardSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = BoardListPagination

    def get_permissions(self):
        if self.action == 'retrieve':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BoardDetailSerializer
        return BoardSerializer

    def get_queryset(self):
        base = (
            Board.objects.annotate(pins_total=Count('pins'))
            .select_related('user', 'user__profile')
            .order_by('-created_at')
        )
        user = self.request.user

        if self.action == 'list':
            if not user.is_authenticated:
                return Board.objects.none()
            return base.filter(Q(user=user) | Q(collaborators=user)).distinct()

        if self.action in ('update', 'partial_update', 'destroy'):
            if not user.is_authenticated:
                return Board.objects.none()
            return base.filter(Q(user=user) | Q(collaborators=user)).distinct()

        if self.action in ('add_pin', 'remove_pin', 'collaborators', 'ordered_pins', 'reorder_pins'):
            if not user.is_authenticated:
                return Board.objects.none()
            return base.filter(Q(user=user) | Q(collaborators=user)).distinct()

        if self.action == 'suggestions':
            if not user.is_authenticated:
                return Board.objects.none()
            return base.filter(user=user)

        if self.action == 'retrieve':
            share_raw = (self.request.query_params.get('share') or '').strip()
            q_share = Q(pk__in=[])
            if share_raw:
                try:
                    uid = uuid.UUID(share_raw)
                    q_share = Q(share_token=uid)
                except ValueError:
                    pass
            q_public = Q(is_private=False)
            if user.is_authenticated:
                q_mine = Q(user=user) | Q(collaborators=user)
                return base.filter(q_public | q_mine | q_share).distinct()
            return base.filter(q_public | q_share).distinct()

        if user.is_authenticated:
            return base.filter(Q(user=user) | Q(collaborators=user)).distinct()
        return Board.objects.none()

    def _can_manage_board_content(self, user, board):
        return board.user == user or board.collaborators.filter(id=user.id).exists()

    def perform_create(self, serializer):
        profile = self.request.user.profile
        limits = profile.board_limits
        is_private = bool(serializer.validated_data.get('is_private', False))
        boards = Board.objects.filter(user=self.request.user)
        private_count = boards.filter(is_private=True).count()
        public_count = boards.filter(is_private=False).count()
        if is_private and limits['private_max'] is not None and private_count >= limits['private_max']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'is_private': f'Private boards limit reached ({limits["private_max"]}).'})
        if not is_private and limits['public_max'] is not None and public_count >= limits['public_max']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'is_private': f'Public boards limit reached ({limits["public_max"]}).'})
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        board = serializer.instance
        if not self._can_manage_board_content(self.request.user, board):
            raise PermissionDenied('Not allowed to edit this board.')
        vd = serializer.validated_data
        if board.user_id != self.request.user.id and 'is_private' in vd:
            vd.pop('is_private')
        if (
            board.user_id == self.request.user.id
            and 'is_private' in vd
            and bool(vd.get('is_private')) != bool(board.is_private)
        ):
            profile = self.request.user.profile
            limits = profile.board_limits
            other_boards = Board.objects.filter(user=self.request.user).exclude(pk=board.pk)
            if vd.get('is_private'):
                n_priv = other_boards.filter(is_private=True).count() + 1
                if limits['private_max'] is not None and n_priv > limits['private_max']:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({'is_private': f'Private boards limit reached ({limits["private_max"]}).'})
            else:
                n_pub = other_boards.filter(is_private=False).count() + 1
                if limits['public_max'] is not None and n_pub > limits['public_max']:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({'is_private': f'Public boards limit reached ({limits["public_max"]}).'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied('Only the board owner can delete this board.')
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='share-token')
    def board_share_token(self, request, pk=None):
        board = self.get_object()
        if board.user_id != request.user.id:
            return Response({'error': 'Only board owner can create share links'}, status=status.HTTP_403_FORBIDDEN)
        regenerate = str(request.data.get('regenerate', '')).lower() in ('true', '1', 'yes')
        if regenerate or board.share_token is None:
            board.share_token = uuid.uuid4()
            board.save(update_fields=['share_token'])
        return Response({'share_token': str(board.share_token)})

    @action(detail=True, methods=['post'], url_path='add-pin')
    def add_pin(self, request, pk=None):
        board = self.get_object()
        if not self._can_manage_board_content(request.user, board):
            return Response({'error': 'Not allowed to edit this board'}, status=status.HTTP_403_FORBIDDEN)
        pin_slug = request.data.get('pin_slug')
        if not pin_slug:
            return Response({'error': 'pin_slug is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pin = Pin.objects.get(slug=pin_slug)
        except Pin.DoesNotExist:
            return Response({'error': 'Pin not found'}, status=status.HTTP_404_NOT_FOUND)
        max_pos = PinBoard.objects.filter(board=board).aggregate(m=Max('position'))['m']
        next_pos = (max_pos if max_pos is not None else -1) + 1
        _, created_pb = PinBoard.objects.get_or_create(
            pin=pin,
            board=board,
            defaults={'position': next_pos},
        )
        status_txt = 'added' if created_pb else 'already_present'
        return Response({'status': status_txt, 'pinCount': board.pins.count()})

    @action(detail=True, methods=['post'], url_path='remove-pin')
    def remove_pin(self, request, pk=None):
        board = self.get_object()
        if not self._can_manage_board_content(request.user, board):
            return Response({'error': 'Not allowed to edit this board'}, status=status.HTTP_403_FORBIDDEN)
        pin_slug = request.data.get('pin_slug')
        if not pin_slug:
            return Response({'error': 'pin_slug is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pin = Pin.objects.get(slug=pin_slug)
        except Pin.DoesNotExist:
            return Response({'error': 'Pin not found'}, status=status.HTTP_404_NOT_FOUND)
        PinBoard.objects.filter(pin=pin, board=board).delete()
        return Response({'status': 'removed', 'pinCount': board.pins.count()})

    @action(detail=True, methods=['get', 'post', 'delete'], url_path='collaborators')
    def collaborators(self, request, pk=None):
        board = self.get_object()
        owner_profile = board.user.profile
        if request.method in ['POST', 'DELETE'] and board.user != request.user:
            return Response({'error': 'Only board owner can manage collaborators'}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'GET':
            return Response({
                'collaborators': [
                    {
                        'id': user.id,
                        'username': user.username,
                    }
                    for user in board.collaborators.order_by('username')
                ],
            })

        if owner_profile.subscription_plan == owner_profile.PLAN_FREE:
            return Response(
                {'error': 'Collaborative boards require Plus or Pro plan'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.method == 'POST':
            username = (request.data.get('username') or '').strip()
            if not username:
                return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                target_user = User.objects.get(username=username)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            if target_user == board.user:
                return Response({'error': 'Board owner cannot be collaborator'}, status=status.HTTP_400_BAD_REQUEST)

            if owner_profile.subscription_plan == owner_profile.PLAN_PLUS and board.collaborators.count() >= 10:
                return Response(
                    {'error': 'Collaborators limit reached (10) for Plus plan'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if board.collaborators.filter(id=target_user.id).exists():
                return Response({'error': 'User is already a collaborator'}, status=status.HTTP_400_BAD_REQUEST)

            if BoardCollaborationInvite.objects.filter(
                board=board,
                invitee=target_user,
                status=BoardCollaborationInvite.STATUS_PENDING,
            ).exists():
                return Response({'error': 'An invitation is already pending for this user'}, status=status.HTTP_400_BAD_REQUEST)

            invite, created = BoardCollaborationInvite.objects.get_or_create(
                board=board,
                invitee=target_user,
                defaults={
                    'invited_by': request.user,
                    'status': BoardCollaborationInvite.STATUS_PENDING,
                },
            )
            if not created:
                invite.invited_by = request.user
                invite.status = BoardCollaborationInvite.STATUS_PENDING
                invite.responded_at = None
                invite.save(update_fields=['invited_by', 'status', 'responded_at'])

            create_localized_notification(
                recipient=target_user,
                sender=request.user,
                notification_type='board_invite',
                title_fr='Invitation tableau',
                message_fr=f"{request.user.username} vous invite à collaborer sur « {board.name} ».",
                action_url='/profile',
                metadata={'invite_id': invite.id, 'board_id': board.id},
            )
            return Response({'status': 'invited', 'invite_id': invite.id, 'collaborator_count': board.collaborators.count()})

        username = (request.data.get('username') or '').strip()
        if not username:
            return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target_user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if not board.collaborators.filter(id=target_user.id).exists():
            return Response({'error': 'Not a collaborator'}, status=status.HTTP_400_BAD_REQUEST)
        board.collaborators.remove(target_user)
        BoardCollaborationInvite.objects.filter(board=board, invitee=target_user).update(
            status=BoardCollaborationInvite.STATUS_DECLINED,
            responded_at=timezone.now(),
        )
        return Response({'status': 'removed', 'collaborator_count': board.collaborators.count()})

    @action(detail=False, methods=['get'], url_path='suggestions')
    def suggestions(self, request):
        """Board names inferred from author's pin topics + existing boards that match."""
        user = request.user
        topic_rows = (
            Pin.objects.filter(author=user)
            .exclude(topic__isnull=True)
            .values('topic_id', 'topic__name', 'topic__slug')
            .annotate(c=Count('id'))
            .order_by('-c')[:14]
        )
        topic_ids = [row['topic_id'] for row in topic_rows if row['topic_id']]
        existing_names = set(Board.objects.filter(user=user).values_list('name', flat=True))
        new_board_hints = []
        seen = set(existing_names)
        for row in topic_rows:
            name = (row['topic__name'] or '').strip()[:255]
            if not name or name.lower() in {x.lower() for x in seen}:
                continue
            seen.add(name)
            new_board_hints.append({
                'name': name,
                'topic_slug': row['topic__slug'],
                'pin_count_hint': row['c'],
            })
        if topic_ids:
            existing_boards_qs = (
                Board.objects.filter(user=user)
                .annotate(
                    overlap_score=Count(
                        'pin_board_memberships',
                        filter=Q(pin_board_memberships__pin__topic_id__in=topic_ids),
                    ),
                    pin_total=Count('pins'),
                )
                .filter(overlap_score__gt=0)
                .order_by('-overlap_score')[:12]
            )
        else:
            existing_boards_qs = Board.objects.none()
        return Response({
            'new_board_hints': new_board_hints[:10],
            'existing_boards': [
                {
                    'id': b.id,
                    'name': b.name,
                    'overlap_score': getattr(b, 'overlap_score', 0),
                    'pin_count': getattr(b, 'pin_total', b.pins.count()),
                }
                for b in existing_boards_qs
            ],
        })

    @action(detail=True, methods=['get'], url_path='ordered-pins')
    def ordered_pins(self, request, pk=None):
        board = self.get_object()
        if not self._can_manage_board_content(request.user, board):
            return Response({'error': 'Not allowed to view this board order'}, status=status.HTTP_403_FORBIDDEN)
        links = PinBoard.objects.filter(board=board).select_related('pin').order_by('position', 'id')
        pins_payload = []
        for link in links:
            pin = link.pin
            img_url = ''
            if pin.image and getattr(pin.image, 'name', ''):
                img_url = build_versioned_media_url(request, pin.image)
            pins_payload.append({
                'id': pin.id,
                'slug': pin.slug,
                'title': pin.title,
                'image': img_url,
                'position': link.position,
                'scheduled_publish_at': pin.scheduled_publish_at.isoformat() if pin.scheduled_publish_at else None,
            })
        return Response({'pins': pins_payload})

    @action(detail=True, methods=['post'], url_path='reorder-pins')
    def reorder_pins(self, request, pk=None):
        board = self.get_object()
        if not self._can_manage_board_content(request.user, board):
            return Response({'error': 'Not allowed to reorder this board'}, status=status.HTTP_403_FORBIDDEN)
        raw_ids = request.data.get('pin_ids')
        if not isinstance(raw_ids, list) or len(raw_ids) == 0:
            return Response({'error': 'pin_ids must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pin_ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError):
            return Response({'error': 'pin_ids must be integers'}, status=status.HTTP_400_BAD_REQUEST)
        current_ids = list(
            PinBoard.objects.filter(board=board).values_list('pin_id', flat=True).order_by('position', 'id'),
        )
        if sorted(pin_ids) != sorted(current_ids):
            return Response(
                {'error': 'pin_ids must match pins on this board exactly'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for idx, pid in enumerate(pin_ids):
            PinBoard.objects.filter(board=board, pin_id=pid).update(position=idx)
        return Response({'status': 'ok'})

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='platform-policy')
    def platform_policy(self, request):
        return Response({
            'ads': {'third_party_tracking': False, 'model': 'freemium_subscription'},
            'creator_credit': {'provenance_chain': False, 'tamper_resistant_hash': False},
        })


class BoardCollaborationInviteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Invitations entrantes pour collaborer sur un board."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BoardCollaborationInviteSerializer

    def get_queryset(self):
        return BoardCollaborationInvite.objects.filter(
            invitee=self.request.user,
            status=BoardCollaborationInvite.STATUS_PENDING,
        ).select_related('board', 'board__user', 'invited_by')

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        invite = (
            BoardCollaborationInvite.objects.select_related('board', 'board__user', 'board__user__profile')
            .filter(
                pk=pk,
                invitee=request.user,
                status=BoardCollaborationInvite.STATUS_PENDING,
            )
            .first()
        )
        if not invite:
            return Response({'error': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)
        owner_profile = invite.board.user.profile
        if owner_profile.subscription_plan == owner_profile.PLAN_FREE:
            return Response(
                {'error': 'Board owner no longer has a collaborative plan'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if owner_profile.subscription_plan == owner_profile.PLAN_PLUS and invite.board.collaborators.count() >= 10:
            return Response(
                {'error': 'Collaborators limit reached on this board'},
                status=status.HTTP_403_FORBIDDEN,
            )
        invite.board.collaborators.add(request.user)
        invite.status = BoardCollaborationInvite.STATUS_ACCEPTED
        invite.responded_at = timezone.now()
        invite.save(update_fields=['status', 'responded_at'])
        Notification.objects.filter(
            recipient=request.user,
            notification_type='board_invite',
        ).filter(metadata__invite_id=invite.id).update(is_read=True)
        return Response({'status': 'accepted', 'board_id': invite.board_id})

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        invite = BoardCollaborationInvite.objects.filter(
            pk=pk,
            invitee=request.user,
            status=BoardCollaborationInvite.STATUS_PENDING,
        ).first()
        if not invite:
            return Response({'error': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)
        invite.status = BoardCollaborationInvite.STATUS_DECLINED
        invite.responded_at = timezone.now()
        invite.save(update_fields=['status', 'responded_at'])
        Notification.objects.filter(
            recipient=request.user,
            notification_type='board_invite',
        ).filter(metadata__invite_id=invite.id).update(is_read=True)
        return Response({'status': 'declined'})


@api_view(['GET'])
@permission_classes([AllowAny])
def legal_document_detail(request, slug):
    if slug not in (LegalDocument.SLUG_PRIVACY, LegalDocument.SLUG_TERMS, LegalDocument.SLUG_CONTACT):
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    lang = request.query_params.get('lang') or 'fr'
    return Response(build_legal_api_response(slug, lang))


@api_view(['GET'])
@permission_classes([AllowAny])
def faq_overview(request):
    lang = request.query_params.get('lang') or 'fr'
    return Response(build_faq_overview_response(lang))
