from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Pin, Comment, Like, Save
from .serializers import PinSerializer, CommentSerializer
from notifications.models import Notification

class PinViewSet(viewsets.ModelViewSet):
    queryset = Pin.objects.all()
    serializer_class = PinSerializer
    lookup_field = 'slug'

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def save(self, request, slug=None):
        pin = self.get_object()
        save, created = Save.objects.get_or_create(user=request.user, pin=pin)
        
        if not created:
            save.delete()
            return Response({'status': 'unsaved', 'saves_count': pin.saves_count})
        
        # Create notification
        if pin.author != request.user:
            Notification.objects.create(
                recipient=pin.author,
                sender=request.user,
                notification_type='save',
                message=f"{request.user.username} a enregistré votre pin: {pin.title}",
                pin_id=pin.id
            )
            
        return Response({'status': 'saved', 'saves_count': pin.saves_count})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, slug=None):
        pin = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, pin=pin)
        
        if not created:
            like.delete()
            return Response({'status': 'unliked', 'likes_count': pin.likes_count})
        
        # Create notification
        if pin.author != request.user:
            Notification.objects.create(
                recipient=pin.author,
                sender=request.user,
                notification_type='like',
                message=f"{request.user.username} a aimé votre pin: {pin.title}",
                pin_id=pin.id
            )
            
        return Response({'status': 'liked', 'likes_count': pin.likes_count})

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, slug=None):
        pin = self.get_object()
        
        if request.method == 'POST':
            text = request.data.get('text')
            if not text:
                return Response({'error': 'Comment text is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            comment = Comment.objects.create(user=request.user, pin=pin, text=text)
            
            # Create notification
            if pin.author != request.user:
                Notification.objects.create(
                    recipient=pin.author,
                    sender=request.user,
                    notification_type='comment',
                    message=f"{request.user.username} a commenté votre pin: {pin.title}",
                    pin_id=pin.id
                )
            
            serializer = CommentSerializer(comment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        # GET comments
        comments = pin.comments.all()
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def recommendations(self, request):
        # 1. Analyser les interactions (Likes et Saves)
        liked_pins = Pin.objects.filter(likes__user=request.user)
        saved_pins = Pin.objects.filter(saves__user=request.user)
        
        # Récupérer tous les pins avec lesquels l'utilisateur a interagi
        interacted_pins = (liked_pins | saved_pins).distinct()
        
        # 2. Extraire les thématiques (topics) et les mots-clés des titres
        topics = interacted_pins.values_list('topic', flat=True).distinct()
        
        # Déterminer les IDs à exclure (déjà aimés ou enregistrés)
        exclude_ids = list(interacted_pins.values_list('id', flat=True))
        
        # 3. Construire la requête de recommandation
        recommendations = Pin.objects.exclude(id__in=exclude_ids).exclude(author=request.user)
        
        if topics.exists():
            # Priorité aux pins partageant les mêmes thématiques
            # On utilise Q pour des filtres complexes si besoin, mais ici simple __in suffit
            from django.db.models import Q
            recommendations = recommendations.filter(topic__in=topics)
            
            # Optionnel : On pourrait aussi chercher par similarité de titre ici
            # titles = interacted_pins.values_list('title', flat=True)
            # ... algorithme plus complexe ...
        
        # 4. Mélanger et paginer
        # '?' est lourd sur de grosses tables, mais OK pour 600 pins
        recommendations = recommendations.order_by('?')
        
        # Fallback si pas assez de recos thématiques
        if recommendations.count() < 20:
            others = Pin.objects.exclude(id__in=exclude_ids).exclude(author=request.user).exclude(id__in=[p.id for p in recommendations]).order_by('?')[:20]
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
        
        pins = Pin.objects.filter(author__in=following_users).order_by('-created_at')
        serializer = self.get_serializer(pins, many=True)
        return Response(serializer.data)
