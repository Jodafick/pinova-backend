import logging
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Comment, Like, Pin, ProcessedAction

logger = logging.getLogger(__name__)

ALLOWED_ACTION_TYPES = {"CREATE_POST", "LIKE_POST", "COMMENT_POST", "DELETE_POST"}


def _to_epoch_ms(dt):
    return int(dt.timestamp() * 1000)


def _pin_payload(pin: Pin) -> dict[str, Any]:
    return {
        "kind": "pin",
        "id": pin.id,
        "slug": pin.slug,
        "title": pin.title,
        "description": pin.description,
        "likes": pin.likes.count(),
        "updatedAt": _to_epoch_ms(pin.updated_at),
        "version": pin.version,
    }


def _comment_payload(comment: Comment) -> dict[str, Any]:
    return {
        "kind": "comment",
        "id": comment.id,
        "pinId": comment.pin_id,
        "text": comment.text,
        "updatedAt": _to_epoch_ms(comment.updated_at),
        "version": comment.version,
    }


class SyncView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        actions = request.data.get("actions")
        if not isinstance(actions, list):
            return Response(
                {"detail": "Le champ actions doit etre une liste."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        conflicts: list[dict[str, Any]] = []
        touched_pin_ids: set[int] = set()
        touched_comment_ids: set[int] = set()

        with transaction.atomic():
            for raw in actions:
                if not isinstance(raw, dict):
                    logger.warning("sync.invalid_action_shape user=%s action=%s", user.id, raw)
                    continue

                action_id = str(raw.get("id") or "").strip()
                action_type = str(raw.get("type") or "").strip()
                client_id = str(raw.get("client_id") or "").strip()
                action_ts = raw.get("timestamp")
                payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}

                if not action_id or action_type not in ALLOWED_ACTION_TYPES or not client_id:
                    logger.warning("sync.invalid_action_fields user=%s action=%s", user.id, raw)
                    continue
                if not isinstance(action_ts, (int, float)):
                    logger.warning("sync.invalid_timestamp user=%s action=%s", user.id, raw)
                    continue

                if ProcessedAction.objects.filter(id=action_id, user=user).exists():
                    continue

                if action_type == "CREATE_POST":
                    title = str(payload.get("title") or "").strip()
                    if not title:
                        logger.warning("sync.create_post_missing_title user=%s action=%s", user.id, action_id)
                        continue
                    slug = str(payload.get("slug") or "").strip() or None
                    description = str(payload.get("content") or payload.get("description") or "").strip()
                    link = str(payload.get("link") or "").strip()
                    pin = Pin(title=title, description=description, link=link, author=user)
                    if slug:
                        pin.slug = slug
                    pin.version = 1
                    pin.save()
                    touched_pin_ids.add(pin.id)

                elif action_type == "LIKE_POST":
                    pin_slug = str(payload.get("pinSlug") or payload.get("pin_slug") or "").strip()
                    if not pin_slug:
                        logger.warning("sync.like_missing_slug user=%s action=%s", user.id, action_id)
                        continue
                    pin = Pin.objects.filter(slug=pin_slug).first()
                    if pin is None:
                        logger.warning("sync.like_pin_not_found user=%s pin=%s", user.id, pin_slug)
                        continue

                    pin_updated_ms = _to_epoch_ms(pin.updated_at)
                    if pin_updated_ms > int(action_ts):
                        conflicts.append(
                            {"actionId": action_id, "reason": "server_newer", "resource": f"pin:{pin.slug}"}
                        )
                        continue

                    liked = bool(payload.get("liked", True))
                    if liked:
                        Like.objects.get_or_create(user=user, pin=pin)
                    else:
                        Like.objects.filter(user=user, pin=pin).delete()
                    pin.version += 1
                    pin.save(update_fields=["version", "updated_at"])
                    touched_pin_ids.add(pin.id)

                elif action_type == "COMMENT_POST":
                    pin_slug = str(payload.get("pinSlug") or payload.get("pin_slug") or "").strip()
                    text = str(payload.get("text") or "").strip()
                    if not pin_slug or not text:
                        logger.warning("sync.comment_missing_fields user=%s action=%s", user.id, action_id)
                        continue
                    pin = Pin.objects.filter(slug=pin_slug).first()
                    if pin is None:
                        logger.warning("sync.comment_pin_not_found user=%s pin=%s", user.id, pin_slug)
                        continue
                    pin_updated_ms = _to_epoch_ms(pin.updated_at)
                    if pin_updated_ms > int(action_ts):
                        conflicts.append(
                            {"actionId": action_id, "reason": "server_newer", "resource": f"pin:{pin.slug}"}
                        )
                        continue
                    comment = Comment.objects.create(user=user, pin=pin, text=text, version=1)
                    pin.version += 1
                    pin.save(update_fields=["version", "updated_at"])
                    touched_pin_ids.add(pin.id)
                    touched_comment_ids.add(comment.id)

                elif action_type == "DELETE_POST":
                    pin_slug = str(payload.get("pinSlug") or payload.get("pin_slug") or "").strip()
                    if not pin_slug:
                        logger.warning("sync.delete_missing_slug user=%s action=%s", user.id, action_id)
                        continue
                    pin = Pin.objects.filter(slug=pin_slug, author=user).first()
                    if pin is None:
                        logger.warning("sync.delete_pin_not_found_or_denied user=%s pin=%s", user.id, pin_slug)
                        continue
                    pin_updated_ms = _to_epoch_ms(pin.updated_at)
                    if pin_updated_ms > int(action_ts):
                        conflicts.append(
                            {"actionId": action_id, "reason": "server_newer", "resource": f"pin:{pin.slug}"}
                        )
                        continue
                    pin.delete()

                ProcessedAction.objects.create(
                    id=action_id,
                    user=user,
                    client_id=client_id,
                    action_type=action_type,
                )

        updated_data: list[dict[str, Any]] = []
        if touched_pin_ids:
            pins = Pin.objects.filter(id__in=touched_pin_ids).prefetch_related("likes")
            updated_data.extend(_pin_payload(pin) for pin in pins)
        if touched_comment_ids:
            comments = Comment.objects.filter(id__in=touched_comment_ids)
            updated_data.extend(_comment_payload(comment) for comment in comments)

        return Response(
            {
                "updatedData": updated_data,
                "conflicts": conflicts,
                "serverTime": _to_epoch_ms(timezone.now()),
            },
            status=status.HTTP_200_OK,
        )
