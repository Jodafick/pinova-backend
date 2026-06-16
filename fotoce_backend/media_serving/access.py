"""Contrôle d'accès aux fichiers ``/media/`` — résolution, signatures HMAC, politique."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpRequest

from accounts.models import Profile
from fotos.models import Comment, Foto, FotoVariant, Topic
from fotos.visibility import (
    pin_is_public_for_media,
    foto_is_visible_for_request,
    pin_media_requires_signed_url,
    profile_media_requires_signed_url,
)

logger = logging.getLogger('fotoce.media.access')

MediaPolicy = Literal['public', 'signed', 'deny']


@dataclass(frozen=True)
class MediaResource:
    kind: str
    relative_path: str
    foto: Foto | None = None
    profile: Profile | None = None
    comment: Comment | None = None


class _ViewerRequest:
    """Minimal request pour réutiliser ``foto_is_visible_for_request``."""

    def __init__(self, user):
        self.user = user


def normalize_relative_media_path(path: str) -> str:
    rel = (path or '').replace('\\', '/').lstrip('/')
    if '..' in rel.split('/'):
        raise ValueError('invalid media path')
    return rel


def safe_join_media_root(relative: str) -> str:
    rel = normalize_relative_media_path(relative)
    root = os.path.normpath(settings.MEDIA_ROOT)
    full = os.path.normpath(os.path.join(root, rel))
    if not full.startswith(root + os.sep) and full != root:
        raise ValueError('path traversal')
    return full


def get_media_signing_secret() -> str:
    return (getattr(settings, 'MEDIA_SIGNING_SECRET', None) or settings.SECRET_KEY or '').encode()


def media_signed_url_ttl() -> int:
    return int(getattr(settings, 'MEDIA_SIGNED_URL_TTL_SECONDS', 3600))


def build_media_signature(relative_path: str, exp: int, user_id: int = 0) -> str:
    rel = normalize_relative_media_path(relative_path)
    payload = f'{rel}:{exp}:{user_id}'.encode()
    return hmac.new(get_media_signing_secret(), payload, hashlib.sha256).hexdigest()


def verify_media_signature(relative_path: str, exp: int, sig: str, user_id: int = 0) -> bool:
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_int < int(time.time()):
        return False
    expected = build_media_signature(relative_path, exp_int, user_id)
    return hmac.compare_digest(str(sig or ''), expected)


def append_signed_query(absolute_url: str, relative_path: str, user_id: int = 0) -> str:
    exp = int(time.time()) + media_signed_url_ttl()
    sig = build_media_signature(relative_path, exp, user_id)
    parts = urlparse(absolute_url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ('exp', 'sig', 'uid')]
    q.extend([('exp', str(exp)), ('sig', sig), ('uid', str(int(user_id or 0)))])
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, urlencode(q), parts.fragment))


def app_media_url(request, relative_path: str) -> str:
    rel = normalize_relative_media_path(relative_path)
    prefix = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return request.build_absolute_uri(f'{prefix}/{rel}')


def resolve_foto_for_media_path(relative_path: str) -> Foto | None:
    rel = normalize_relative_media_path(relative_path)
    qs = Foto.objects.select_related('author', 'author__profile')
    if rel.startswith('story_videos/'):
        return qs.filter(story_video=rel).first()
    if rel.startswith('pins/variants/'):
        variant = (
            FotoVariant.objects.filter(image=rel)
            .select_related('pin', 'pin__author', 'pin__author__profile')
            .first()
        )
        return variant.pin if variant else None
    if rel.startswith('pins/') or rel.startswith('pin_download_variants/'):
        foto = qs.filter(image=rel).first()
        if foto:
            return foto
        variant = (
            FotoVariant.objects.filter(image=rel)
            .select_related('pin', 'pin__author', 'pin__author__profile')
            .first()
        )
        return variant.pin if variant else None
    return None


def resolve_profile_for_media_path(relative_path: str) -> Profile | None:
    rel = normalize_relative_media_path(relative_path)
    if rel.startswith('avatars/'):
        return Profile.objects.filter(avatar=rel).select_related('user').first()
    if rel.startswith('covers/'):
        return Profile.objects.filter(cover_image=rel).select_related('user').first()
    return None


def resolve_comment_for_media_path(relative_path: str) -> Comment | None:
    rel = normalize_relative_media_path(relative_path)
    if not rel.startswith('comments/'):
        return None
    return (
        Comment.objects.filter(media=rel)
        .select_related('pin', 'pin__author', 'pin__author__profile')
        .first()
    )


def resolve_media_resource(relative_path: str) -> MediaResource | None:
    rel = normalize_relative_media_path(relative_path)
    foto = resolve_foto_for_media_path(rel)
    if foto:
        return MediaResource(kind='pin', relative_path=rel, foto=pin)
    profile = resolve_profile_for_media_path(rel)
    if profile:
        return MediaResource(kind='profile', relative_path=rel, profile=profile)
    comment = resolve_comment_for_media_path(rel)
    if comment:
        return MediaResource(kind='comment', relative_path=rel, comment=comment, foto=comment.pin)
    if rel.startswith('topic_covers/'):
        if Topic.objects.filter(cover_image=rel).exists():
            return MediaResource(kind='topic_cover', relative_path=rel)
    if rel.startswith(('partner_ads/', 'creator_ads/')):
        return MediaResource(kind='ad', relative_path=rel)
    return None


def media_policy(resource: MediaResource | None, *, viewer_user_id: int | None = None) -> MediaPolicy:
    if resource is None:
        return 'deny'
    if resource.kind in ('topic_cover', 'ad'):
        return 'public'
    if resource.kind == 'pin' and resource.pin:
        if pin_is_public_for_media(resource.pin):
            return 'public'
        return 'signed'
    if resource.kind == 'profile' and resource.profile:
        if profile_media_requires_signed_url(resource.profile, viewer_user_id=viewer_user_id):
            return 'signed'
        return 'public'
    if resource.kind == 'comment' and resource.pin:
        if pin_is_public_for_media(resource.pin):
            return 'public'
        return 'signed'
    return 'deny'


def viewer_request_for_user_id(user_id: int | None) -> _ViewerRequest:
    if user_id:
        user = User.objects.filter(pk=user_id).select_related('profile').first()
        if user is not None:
            return _ViewerRequest(user)
    return _ViewerRequest(AnonymousUser())


def media_visible_for_viewer(resource: MediaResource, request: HttpRequest, *, uid: int | None = None) -> bool:
    viewer_id = uid
    if viewer_id is None and request.user.is_authenticated:
        viewer_id = request.user.id
    viewer_req = viewer_request_for_user_id(viewer_id)

    if resource.kind == 'pin' and resource.pin:
        return foto_is_visible_for_request(resource.pin, viewer_req)
    if resource.kind == 'comment' and resource.pin:
        return foto_is_visible_for_request(resource.pin, viewer_req)
    if resource.kind == 'profile' and resource.profile:
        profile = resource.profile
        if not profile_media_requires_signed_url(profile, viewer_user_id=viewer_id):
            return True
        if viewer_id and viewer_id == profile.user_id:
            return True
        if viewer_id:
            viewer_profile = Profile.objects.filter(user_id=viewer_id).first()
            if viewer_profile and profile.followers.filter(pk=viewer_profile.pk).exists():
                return True
        return False
    if resource.kind in ('topic_cover', 'ad'):
        return True
    return False


def evaluate_media_access(request: HttpRequest, relative_path: str) -> tuple[bool, str, MediaResource | None]:
    """
    Retourne (allowed, reason, resource).
    reason : public | signed_ok | signed_invalid | visibility_denied | unknown | path_invalid
    """
    try:
        rel = normalize_relative_media_path(relative_path)
        safe_join_media_root(rel)
    except ValueError:
        return False, 'path_invalid', None

    resource = resolve_media_resource(rel)
    policy = media_policy(resource)

    if policy == 'deny':
        logger.info(
            'media_access_denied',
            extra={'path': rel, 'reason': 'unknown', 'flow': 'media'},
        )
        return False, 'unknown', resource

    if policy == 'public':
        if resource and resource.kind in ('pin', 'comment') and resource.pin:
            if not foto_is_visible_for_request(resource.pin, request):
                return False, 'visibility_denied', resource
        return True, 'public', resource

    exp = request.GET.get('exp')
    sig = request.GET.get('sig')
    try:
        uid = int(request.GET.get('uid') or 0)
    except (TypeError, ValueError):
        uid = 0

    if not verify_media_signature(rel, exp or 0, sig or '', uid):
        return False, 'signed_invalid', resource

    if resource and not media_visible_for_viewer(resource, request, uid=uid):
        return False, 'visibility_denied', resource

    return True, 'signed_ok', resource


def media_requires_signed_url(relative_path: str, *, foto: Foto | None = None, profile: Profile | None = None) -> bool:
    rel = normalize_relative_media_path(relative_path)
    if foto is None:
        foto = resolve_foto_for_media_path(rel)
    if foto is not None:
        return pin_media_requires_signed_url(foto)
    if profile is None:
        profile = resolve_profile_for_media_path(rel)
    if profile is not None:
        return profile_media_requires_signed_url(profile)
    comment = resolve_comment_for_media_path(rel)
    if comment:
        return pin_media_requires_signed_url(comment.pin)
    resource = resolve_media_resource(rel)
    return media_policy(resource) == 'signed'
