from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from django.contrib.auth.models import User
from asgiref.sync import async_to_sync
from googletrans import Translator
import hashlib
import json
import re
from .models import Pin, Comment, Like, Save, Hashtag, PrivatePinTag, PinProvenanceEvent, Board
from .serializers import PinSerializer, CommentSerializer, BoardSerializer, extract_hashtags
from .translation import translate_text_to, detect_original_language
from notifications.models import Notification


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

    def get_queryset(self):
        queryset = (
            Pin.objects.select_related('author', 'author__profile')
            .prefetch_related('hashtags')
            .all()
            .order_by('-created_at')
        )
        topic = self.request.query_params.get('topic')
        if topic:
            queryset = queryset.filter(topic=topic)
        if not self.request.user.is_authenticated:
            return queryset.filter(visibility=Pin.VISIBILITY_PUBLIC)
        my_profile = self.request.user.profile
        return queryset.filter(
            Q(visibility=Pin.VISIBILITY_PUBLIC)
            | Q(author=self.request.user)
            | Q(visibility=Pin.VISIBILITY_FOLLOWERS, author__profile__followers=my_profile)
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

        if pin.author != request.user:
            Notification.objects.create(
                recipient=pin.author,
                sender=request.user,
                notification_type='save',
                message=f"{request.user.username} a enregistré votre pin: {pin.title}",
                pin_id=pin.id,
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
            )

        return Response({'status': 'liked', 'likes_count': pin.likes_count})

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, slug=None):
        pin = self.get_object()

        if request.method == 'POST':
            text = request.data.get('text', '')
            gif_url = request.data.get('gif')
            parent_id = request.data.get('parentId') or request.data.get('parent')
            if not text and not gif_url:
                return Response({'error': 'Comment text is required'}, status=status.HTTP_400_BAD_REQUEST)
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
                parent=parent,
                original_language=detect_original_language(text),
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
                        )

            if pin.author != request.user:
                Notification.objects.create(
                    recipient=pin.author,
                    sender=request.user,
                    notification_type='comment',
                    message=f"{request.user.username} a commenté votre pin: {pin.title}",
                    pin_id=pin.id,
                )

            serializer = CommentSerializer(comment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        comments = (
            pin.comments.filter(parent__isnull=True)
            .select_related('user', 'user__profile')
            .prefetch_related('replies', 'hashtags')
        )
        serializer = CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def recommendations(self, request):
        base_queryset = self.get_queryset()
        liked_pins = base_queryset.filter(likes__user=request.user)
        saved_pins = base_queryset.filter(saves__user=request.user)
        interacted_pins = (liked_pins | saved_pins).distinct()
        topics = interacted_pins.values_list('topic', flat=True).distinct()
        exclude_ids = list(interacted_pins.values_list('id', flat=True))
        recommendations = base_queryset.exclude(id__in=exclude_ids).exclude(author=request.user)

        if topics.exists():
            recommendations = recommendations.filter(topic__in=topics)

        recommendations = recommendations.order_by('?')

        if recommendations.count() < 20:
            others = (
                base_queryset.exclude(id__in=exclude_ids)
                .exclude(author=request.user)
                .exclude(id__in=[p.id for p in recommendations])
                .order_by('?')[:20]
            )
            recommendations = list(recommendations) + list(others)

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
        pins = self.get_queryset().filter(author__in=following_users).exclude(visibility=Pin.VISIBILITY_PRIVATE).order_by('-created_at')
        serializer = self.get_serializer(pins, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def topics(self, request):
        topics_qs = (
            Pin.objects.exclude(topic__isnull=True)
            .exclude(topic__exact='')
            .values('topic')
            .annotate(pin_count=Count('id'))
            .order_by('-pin_count', 'topic')
        )
        target_lang = (request.query_params.get('lang') or '').lower()
        if not target_lang and request.user.is_authenticated:
            target_lang = (request.user.profile.preferred_language or '').lower()
        items = [{'name': item['topic'], 'pinCount': item['pin_count']} for item in topics_qs]
        if target_lang and target_lang not in ('fr', 'auto'):
            translator = Translator()
            translated = []
            for item in items:
                try:
                    translated_name = async_to_sync(translate_text_to)(translator, item['name'], target_lang)
                    translated.append({**item, 'name': translated_name})
                except RuntimeError:
                    translated.append(item)
            return Response(translated)
        return Response(items)

    @action(detail=True, methods=['get', 'post', 'delete'], permission_classes=[permissions.IsAuthenticated], url_path='private-tags')
    def private_tags(self, request, slug=None):
        pin = self.get_object()
        if pin.author != request.user:
            return Response({'error': 'Only pin owner can manage private tags'}, status=status.HTTP_403_FORBIDDEN)
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

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly], url_path='translate-description')
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

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly], url_path='comments/(?P<comment_id>[^/.]+)/translate')
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
        comment.translated_text = translated
        comment.save(update_fields=['translated_text'])
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
            Board.objects.filter(user=self.request.user)
            .annotate(pin_count=Count('pins'))
            .order_by('-created_at')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='add-pin')
    def add_pin(self, request, pk=None):
        board = self.get_object()
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
        pin_slug = request.data.get('pin_slug')
        if not pin_slug:
            return Response({'error': 'pin_slug is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pin = Pin.objects.get(slug=pin_slug)
        except Pin.DoesNotExist:
            return Response({'error': 'Pin not found'}, status=status.HTTP_404_NOT_FOUND)
        board.pins.remove(pin)
        return Response({'status': 'removed', 'pinCount': board.pins.count()})

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='platform-policy')
    def platform_policy(self, request):
        return Response({
            'ads': {'third_party_tracking': False, 'model': 'freemium_subscription'},
            'creator_credit': {'provenance_chain': True, 'tamper_resistant_hash': True},
        })
