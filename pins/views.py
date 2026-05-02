from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q, Case, When, Value, IntegerField
from django.contrib.auth.models import User
from asgiref.sync import async_to_sync
from googletrans import Translator
import hashlib
import json
import re
from .models import (
    Pin,
    Topic,
    Comment,
    Like,
    Save,
    Hashtag,
    PrivatePinTag,
    PinProvenanceEvent,
    Board,
    CommentLike,
    TopicTranslation,
    PinViewEvent,
    SearchInteraction,
)
from .serializers import PinSerializer, CommentSerializer, BoardSerializer, extract_hashtags
from .translation import translate_text_to, detect_original_language
from notifications.models import Notification


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

    def _resolve_target_lang(self, request):
        explicit = request.data.get('target_lang') or request.query_params.get('target_lang')
        if explicit:
            return str(explicit).strip().lower()
        if request.user.is_authenticated:
            return (request.user.profile.preferred_language or 'fr').lower()
        return 'fr'

    def _ordered_by_topic_score(self, queryset, topic_scores):
        if not topic_scores:
            return list(queryset.order_by('-created_at'))
        items = list(queryset)
        items.sort(
            key=lambda pin: (
                topic_scores.get(self._pin_topic_name(pin), 0),
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

    def get_queryset(self):
        queryset = (
            Pin.objects.select_related('author', 'author__profile', 'topic')
            .prefetch_related('hashtags')
            .all()
            .order_by('-created_at')
        )
        topic = self.request.query_params.get('topic')
        queryset = self._apply_topic_filter(queryset, topic)
        if not self.request.user.is_authenticated:
            return queryset.filter(
                visibility=Pin.VISIBILITY_PUBLIC,
                author__profile__private_profile=False,
            )
        my_profile = self.request.user.profile
        return queryset.filter(
            Q(visibility=Pin.VISIBILITY_PUBLIC, author__profile__private_profile=False)
            | Q(author=self.request.user)
            | Q(visibility=Pin.VISIBILITY_FOLLOWERS, author__profile__followers=my_profile)
            | Q(author__profile__private_profile=True, author__profile__followers=my_profile)
        ).distinct()

    def perform_create(self, serializer):
        pin = serializer.save(author=self.request.user)
        image_hash = hashlib.sha256()
        for chunk in pin.image.chunks():
            image_hash.update(chunk)
        root_hash = image_hash.hexdigest()
        pin.provenance_root_hash = root_hash
        pin.save(update_fields=['provenance_root_hash'])
        PinProvenanceEvent.objects.create(
            pin=pin,
            actor=self.request.user,
            action=PinProvenanceEvent.ACTION_CREATE,
            previous_hash='',
            current_hash=root_hash,
            metadata={'title': pin.title, 'visibility': pin.visibility},
        )

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def save(self, request, slug=None):
        pin = self.get_object()
        save, created = Save.objects.get_or_create(user=request.user, pin=pin)

        if not created:
            save.delete()
            return Response({'status': 'unsaved', 'saves_count': pin.saves_count})

        latest = pin.provenance_events.order_by('-created_at').first()
        previous_hash = latest.current_hash if latest else pin.provenance_root_hash
        payload = json.dumps({'pin': pin.id, 'user': request.user.id, 'action': 'save'}, sort_keys=True)
        current_hash = hashlib.sha256(f"{previous_hash}:{payload}".encode('utf-8')).hexdigest()
        PinProvenanceEvent.objects.create(
            pin=pin,
            actor=request.user,
            action=PinProvenanceEvent.ACTION_SAVE,
            previous_hash=previous_hash,
            current_hash=current_hash,
            metadata={'saved_by': request.user.username},
        )

        if pin.author != request.user and pin.author.profile.notifications_saves:
            Notification.objects.create(
                recipient=pin.author,
                sender=request.user,
                notification_type='save',
                message=f"{request.user.username} a enregistré votre pin: {pin.title}",
                pin_id=pin.id,
                pin_slug=pin.slug,
            )

        return Response({'status': 'saved', 'saves_count': pin.saves_count})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, slug=None):
        pin = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, pin=pin)

        if not created:
            like.delete()
            return Response({'status': 'unliked', 'likes_count': pin.likes_count})

        if pin.author != request.user:
            Notification.objects.create(
                recipient=pin.author,
                sender=request.user,
                notification_type='like',
                message=f"{request.user.username} a aimé votre pin: {pin.title}",
                pin_id=pin.id,
                pin_slug=pin.slug,
            )

        return Response({'status': 'liked', 'likes_count': pin.likes_count})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='view')
    def view_event(self, request, slug=None):
        pin = self.get_object()
        PinViewEvent.objects.create(user=request.user, pin=pin)
        return Response({'status': 'recorded'})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='search-interactions')
    def search_interactions(self, request):
        query = (request.data.get('query') or '').strip()
        if len(query) < 2:
            return Response({'status': 'ignored'})
        SearchInteraction.objects.create(user=request.user, query=query[:120])
        return Response({'status': 'recorded'})

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, slug=None):
        pin = self.get_object()

        if request.method == 'POST':
            text = (request.data.get('text', '') or '').strip()
            gif_url = request.data.get('gif')
            media_file = request.FILES.get('media')
            parent_id = request.data.get('parentId') or request.data.get('parent')
            if not text and not gif_url and not media_file:
                return Response({'error': 'Comment text, gif or media is required'}, status=status.HTTP_400_BAD_REQUEST)
            if media_file:
                if not str(getattr(media_file, 'content_type', '')).startswith('image/'):
                    return Response({'error': 'Only image files are allowed'}, status=status.HTTP_400_BAD_REQUEST)
                if media_file.size > 5 * 1024 * 1024:
                    return Response({'error': 'Media file must be <= 5MB'}, status=status.HTTP_400_BAD_REQUEST)
            is_gif_media = str(getattr(media_file, 'content_type', '')).lower() == 'image/gif' if media_file else False
            if (gif_url or is_gif_media) and not request.user.profile.can_use_comment_gifs:
                return Response(
                    {'error': 'GIF comments require Plus or Pro plan'},
                    status=status.HTTP_403_FORBIDDEN,
                )
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
                        Notification.objects.create(
                            recipient=mentioned_user,
                            sender=request.user,
                            notification_type='comment',
                            message=f"{request.user.username} vous a mentionné dans un commentaire.",
                            pin_id=pin.id,
                            pin_slug=pin.slug,
                            comment_id=comment.id,
                        )

            if parent and parent.user != request.user:
                Notification.objects.create(
                    recipient=parent.user,
                    sender=request.user,
                    notification_type='comment',
                    message=f"{request.user.username} a répondu à votre commentaire sur {pin.title}.",
                    pin_id=pin.id,
                    pin_slug=pin.slug,
                    comment_id=comment.id,
                )

            if pin.author != request.user and not (parent and parent.user == pin.author):
                Notification.objects.create(
                    recipient=pin.author,
                    sender=request.user,
                    notification_type='comment',
                    message=f"{request.user.username} a commenté votre pin: {pin.title}",
                    pin_id=pin.id,
                    pin_slug=pin.slug,
                    comment_id=comment.id,
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
            .select_related('user', 'user__profile')
            .prefetch_related('replies', 'replies__user', 'replies__user__profile', 'hashtags')
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
            .select_related('user', 'user__profile')
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
            Notification.objects.create(
                recipient=comment.user,
                sender=request.user,
                notification_type='like',
                message=f"{request.user.username} a aimé votre commentaire.",
                pin_id=comment.pin_id,
                pin_slug=comment.pin.slug,
                comment_id=comment.id,
            )

        return Response({'status': 'liked', 'likes_count': comment.comment_likes.count()})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def recommendations(self, request):
        base_queryset = self.get_queryset().exclude(author=request.user)
        topic_scores = self._build_topic_scores(request.user)
        recommendations = self._ordered_by_topic_score(base_queryset, topic_scores)
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
            .order_by('-created_at')
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
        page = self.paginate_queryset(queryset.order_by('-created_at'))
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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
        following_items = list(following_queryset.order_by('-created_at'))
        discover_items = self._ordered_by_topic_score(discover_queryset, topic_scores)

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
        page = self.paginate_queryset(mixed)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(mixed, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def topics(self, request):
        limit_raw = (request.query_params.get('limit') or '10').strip()
        limit = int(limit_raw) if limit_raw.isdigit() else 10
        limit = max(1, min(limit, 30))
        search_query = (request.query_params.get('q') or '').strip()
        search_query_lower = search_query.lower()

        base_qs = (
            Pin.objects.exclude(topic__isnull=True)
            .exclude(visibility=Pin.VISIBILITY_PRIVATE)
        )
        topics_qs = (
            Topic.objects.filter(is_active=True)
            .annotate(
                pin_count=Count(
                    'pins',
                    filter=~Q(pins__visibility=Pin.VISIBILITY_PRIVATE),
                    distinct=True,
                )
            )
            .filter(pin_count__gt=0)
            .order_by('-pin_count', 'name')
            .values('id', 'name', 'slug', 'icon', 'color', 'pin_count')
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

        target_lang = (request.query_params.get('lang') or '').lower()
        if not target_lang and request.user.is_authenticated:
            target_lang = (request.user.profile.preferred_language or '').lower()
        items = []
        translator = Translator() if target_lang and target_lang not in ('fr', 'auto') else None
        supported_langs = ['fr', 'en', 'es', 'de', 'it', 'pt', 'ar', 'ja', 'zh', 'fon']
        for item in topics_qs:
            topic_name = item['name']
            record, _ = TopicTranslation.objects.get_or_create(
                topic=topic_name,
                defaults={'translations': {'fr': topic_name}},
            )
            translations = dict(record.translations or {})
            if 'fr' not in translations:
                translations['fr'] = topic_name
            if translator and target_lang in supported_langs and target_lang not in translations:
                try:
                    translated_name = async_to_sync(translate_text_to)(translator, topic_name, target_lang)
                    translations[target_lang] = translated_name
                    record.translations = translations
                    record.save(update_fields=['translations', 'updated_at'])
                except RuntimeError:
                    pass
            display_name = topic_name
            if target_lang and target_lang not in ('auto', 'fr'):
                display_name = translations.get(target_lang, topic_name)
            if search_query_lower:
                if not (
                    search_query_lower in topic_name.lower()
                    or search_query_lower in display_name.lower()
                    or any(search_query_lower in str(value).lower() for value in translations.values())
                ):
                    continue
            items.append({
                'name': display_name,
                'originalName': topic_name,
                'slug': item['slug'],
                'icon': item['icon'],
                'color': item['color'],
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
        return Response({
            'download_url': request.build_absolute_uri(pin.image.url),
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
        my_pins = Pin.objects.filter(author=request.user)
        totals = my_pins.aggregate(
            pins=Count('id'),
            likes=Count('likes', distinct=True),
            saves=Count('saves', distinct=True),
            comments=Count('comments', distinct=True),
            views=Count('view_events', distinct=True),
        )
        top_pins = (
            my_pins.annotate(
                likes_total=Count('likes', distinct=True),
                saves_total=Count('saves', distinct=True),
                views_total=Count('view_events', distinct=True),
            )
            .order_by('-views_total', '-saves_total', '-likes_total', '-created_at')[:5]
        )
        return Response({
            'totals': totals,
            'top_pins': [
                {
                    'id': pin.id,
                    'slug': pin.slug,
                    'title': pin.title,
                    'likes': pin.likes_total,
                    'saves': pin.saves_total,
                    'views': pin.views_total,
                }
                for pin in top_pins
            ],
        })

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def provenance(self, request, slug=None):
        pin = self.get_object()
        events = pin.provenance_events.select_related('actor').order_by('created_at')
        return Response({
            'root_hash': pin.provenance_root_hash,
            'events': [
                {
                    'id': event.id,
                    'actor': event.actor.username,
                    'action': event.action,
                    'previous_hash': event.previous_hash,
                    'current_hash': event.current_hash,
                    'metadata': event.metadata,
                    'created_at': event.created_at,
                }
                for event in events
            ],
        })

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
            comment = Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
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

    def get_queryset(self):
        return (
            Board.objects.filter(Q(user=self.request.user) | Q(collaborators=self.request.user))
            .annotate(pin_count=Count('pins'))
            .distinct()
            .order_by('-created_at')
        )

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
        board.pins.add(pin)
        return Response({'status': 'added', 'pinCount': board.pins.count()})

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
        board.pins.remove(pin)
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

            board.collaborators.add(target_user)
            return Response({'status': 'added', 'collaborator_count': board.collaborators.count()})

        username = (request.data.get('username') or '').strip()
        if not username:
            return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)
        board.collaborators.filter(username=username).delete()
        return Response({'status': 'removed', 'collaborator_count': board.collaborators.count()})

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='platform-policy')
    def platform_policy(self, request):
        return Response({
            'ads': {'third_party_tracking': False, 'model': 'freemium_subscription'},
            'creator_credit': {'provenance_chain': True, 'tamper_resistant_hash': True},
        })
