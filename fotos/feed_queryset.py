"""Queryset feed : annotations viewer + prefetch relations (évite N+1 sérialisation)."""

from __future__ import annotations

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Profile

from .models import Comment, ContentReport, Like, Foto, FotoBoard, Save

FEED_VIEW_ACTIONS = frozenset({
    'list',
    'discover',
    'header_search',
    'recommendations',
    'following',
    'home_feed',
})


def _relation_count_subquery(model, *, pin_field='foto_id'):
    return Subquery(
        model.objects.filter(**{pin_field: OuterRef('pk')})
        .values(pin_field)
        .annotate(_c=Count('pk'))
        .values('_c')[:1],
        output_field=IntegerField(),
    )


def cache_viewer_following_profile_ids(request) -> frozenset[int]:
    """Une requête par requête HTTP — réutilisée pour is_following et filtres following."""
    cached = getattr(request, '_viewer_following_profile_ids', None)
    if cached is not None:
        return cached
    if not request.user.is_authenticated:
        ids: frozenset[int] = frozenset()
    else:
        ids = frozenset(request.user.profile.following.values_list('pk', flat=True))
    request._viewer_following_profile_ids = ids
    return ids


def annotate_foto_feed(queryset, user):
    """
    Annotate is_liked, is_saved, is_boosted, counts et can_comment sur le queryset parent.
    Subquery counts : compatibles avec .distinct() du filtre visibilité.
    """
    queryset = queryset.annotate(
        _feed_likes_count=Coalesce(_relation_count_subquery(Like), Value(0), output_field=IntegerField()),
        _feed_comments_count=Coalesce(_relation_count_subquery(Comment), Value(0), output_field=IntegerField()),
        _feed_saves_count=Coalesce(_relation_count_subquery(Save), Value(0), output_field=IntegerField()),
    )

    if user and user.is_authenticated:
        viewer_profile_id = user.profile.pk
        now = timezone.now()
        from monetization.models import FotoBoost

        follower_exists = Exists(
            Profile.followers.through.objects.filter(
                from_profile_id=viewer_profile_id,
                to_profile_id=OuterRef('author__profile__pk'),
            )
        )
        extra: dict = {
            '_is_liked': Exists(Like.objects.filter(user_id=user.id, foto_id=OuterRef('pk'))),
            '_is_saved': Exists(Save.objects.filter(user_id=user.id, foto_id=OuterRef('pk'))),
            '_is_boosted': Exists(
                FotoBoost.objects.filter(
                    foto_id=OuterRef('pk'),
                    status=FotoBoost.STATUS_ACTIVE,
                    ends_at__gt=now,
                )
            ),
            '_can_comment': Case(
                When(author_id=user.id, then=Value(True)),
                When(comments_policy=Foto.COMMENTS_CLOSED, then=Value(False)),
                When(comments_policy=Foto.COMMENTS_OPEN, then=Value(True)),
                When(comments_policy=Foto.COMMENTS_FOLLOWERS_ONLY, then=follower_exists),
                default=Value(False),
                output_field=BooleanField(),
            ),
        }
        if '_viewer_has_reported_pin' not in getattr(queryset.query, 'annotations', {}):
            extra['_viewer_has_reported_pin'] = Exists(
                ContentReport.objects.filter(
                    reporter_id=user.id,
                    foto_id=OuterRef('pk'),
                )
            )
        queryset = queryset.annotate(**extra)
    else:
        queryset = queryset.annotate(
            _is_liked=Value(False, output_field=BooleanField()),
            _is_saved=Value(False, output_field=BooleanField()),
            _is_boosted=Value(False, output_field=BooleanField()),
            _can_comment=Value(False, output_field=BooleanField()),
        )

    return queryset


def prefetch_foto_feed_relations(queryset):
    """FotoBoard + hashtags + variant_assets en une passe prefetch."""
    return queryset.prefetch_related(
        'hashtags',
        'variant_assets',
        Prefetch(
            'foto_board_memberships',
            queryset=FotoBoard.objects.select_related('board').order_by('position', 'id'),
        ),
    )


def optimize_foto_feed_queryset(queryset, request):
    """Applique annotations + prefetch pour les endpoints feed."""
    user = request.user if request.user.is_authenticated else None
    if user is not None:
        cache_viewer_following_profile_ids(request)
    queryset = annotate_foto_feed(queryset, user)
    return prefetch_foto_feed_relations(queryset)


def feed_serializer_context(request, base_context: dict | None = None) -> dict:
    """Contexte FotoSerializer feed : following pré-chargé pour is_following."""
    ctx = dict(base_context or {})
    ctx['feed_mode'] = True
    if request.user.is_authenticated:
        ctx['_viewer_following_profile_ids'] = cache_viewer_following_profile_ids(request)
    else:
        ctx['_viewer_following_profile_ids'] = frozenset()
    return ctx
