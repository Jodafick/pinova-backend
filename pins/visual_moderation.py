"""
Politique modération média façon flux social (tolérance « sexy » / flou nu–porn léger /
file d’attente staff si trop explicite). Appel ONNX via ``nsfw_inference``.

Si aucun modèle ONNX configuré → pas de mise à jour auto (blur/needs_review inchangés
hors champ client).

Les mineurs : les contenus classés hors « glamour safe » peuvent être rejetés (400).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image
from rest_framework import serializers as drf_serializers

from .nsfw_inference import classify_pil_rgb_scores

logger = logging.getLogger(__name__)

try:
    import cv2  # type: ignore[import-untyped]

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


@dataclass
class VisualModerationDecision:
    force_blur: bool
    needs_staff_review: bool
    minor_reject: bool
    aggregated: dict[str, float] | None


def _global_score(s: dict[str, float]) -> float:
    return float(s.get('porn', 0) + s.get('hentai', 0) + s.get('sexy', 0) * 0.2)


def _glamour_pass(scores: dict[str, float]) -> bool:
    porn = float(scores.get('porn', 0))
    hentai = float(scores.get('hentai', 0))
    sexy = float(scores.get('sexy', 0))
    if sexy < 0.5:
        return False
    if sexy >= 0.62 and porn < 0.8 and hentai < 0.68 and sexy >= porn * 1.04:
        return True
    if sexy >= 0.52 and sexy >= porn * 1.12 and porn < 0.72 and hentai < 0.58:
        return True
    return False


def policy_from_scores(verified_adult: bool, scores: dict[str, float]) -> VisualModerationDecision:
    """Alignée sur classifyNsfwScores (frontend) mais « block » majeur → file staff + blur."""
    porn = float(scores.get('porn', 0))
    hentai = float(scores.get('hentai', 0))
    sexy = float(scores.get('sexy', 0))
    drawing = float(scores.get('drawing', 0))
    gs = _global_score(scores)
    glamour = _glamour_pass(scores)

    t_p_soft = 0.5
    t_h_soft = 0.45
    t_hp = 0.91
    t_hh = 0.82
    t_gs_block = 1.38
    t_gs_bl_lo = 0.72
    t_art = 0.85

    elevated = (
        porn >= t_p_soft or hentai >= t_h_soft or (sexy >= 0.74 and not glamour)
    )

    if drawing >= t_art and not elevated:
        return VisualModerationDecision(False, False, False, scores)

    if glamour and porn < t_hp and hentai < t_hh:
        return VisualModerationDecision(False, False, False, scores)

    hard_explicit = (
        porn >= t_hp
        or hentai >= t_hh
        or (gs >= t_gs_block and not glamour)
    )
    blur_corridor = (
        not glamour
        and (
            (t_p_soft <= porn < t_hp)
            or (t_h_soft <= hentai < t_hh)
            or (t_gs_bl_lo <= gs < t_gs_block)
        )
    )

    if not verified_adult:
        if glamour and porn < 0.78 and hentai < 0.62:
            return VisualModerationDecision(False, False, False, scores)
        safe_minor = (
            porn < t_p_soft - 0.06
            and hentai < t_h_soft - 0.06
            and gs < t_gs_bl_lo - 0.08
            and not blur_corridor
        )
        if not safe_minor:
            return VisualModerationDecision(True, False, True, scores)
        return VisualModerationDecision(False, False, False, scores)

    if hard_explicit:
        return VisualModerationDecision(True, True, False, scores)

    if blur_corridor:
        return VisualModerationDecision(True, False, False, scores)

    return VisualModerationDecision(False, False, False, scores)


def _pil_from_field_any(field_file) -> Image.Image | None:
    try:
        if field_file is None or not getattr(field_file, 'name', ''):
            return None
        if hasattr(field_file, 'path'):  # local storage FileField après save()
            path = getattr(field_file, 'path')
            if path:
                return Image.open(path).convert('RGB')
    except Exception as exc:
        logger.debug('_pil_from_field path read %s', exc)
    try:
        field_file.open('rb')
        try:
            data = field_file.read()
        finally:
            field_file.close()
        try:
            field_file.seek(0)
        except (AttributeError, OSError):
            pass
        if not data:
            return None
        return Image.open(io.BytesIO(data)).convert('RGB')
    except Exception as exc:
        logger.warning('Lecture média PIN pour modération impossible : %s', exc)
        return None


def _video_rgb_frames(media_field, max_frames: int = 6):
    frames: list[Image.Image] = []
    if not HAS_CV2:
        logger.warning('OpenCV absent : pas d’échantillonnage vidéo backend.')
        return frames
    local_path = None
    tmp_path = None
    try:
        if hasattr(media_field, 'path') and getattr(media_field, 'path', None):
            local_path = media_field.path
        else:
            import tempfile

            suf = '.' + ((getattr(media_field, 'name', '') or '').rsplit('.', 1)[-1] or 'mp4')
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=suf)
            tmp_path = tf.name
            media_field.open('rb')
            for ch in media_field.chunks():
                tf.write(ch)
            tf.close()
            media_field.close()
            local_path = tmp_path

        cap = cv2.VideoCapture(local_path or '')
        if not cap.isOpened():
            return frames
        fc = max(1.0, float(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        ix = sorted({int(fc * i / max_frames) for i in range(max_frames)})
        for fi in ix:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok, raw = cap.read()
            if not ok or raw is None:
                continue
            rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))
        cap.release()
    except Exception as exc:
        logger.warning('Échantillonnage vidéo modération : %s', exc)
    finally:
        if tmp_path:
            try:
                import os as _os

                _os.unlink(tmp_path)
            except OSError:
                pass
    return frames


def classify_pin_visual(pin, verified_adult: bool) -> VisualModerationDecision | None:
    """
    Retourne une décision si le modèle répond ; ``None`` si ONNX indisponible / erreur lecture.
    """
    score_batches: list[dict[str, float]] = []
    if getattr(pin, 'image', None) and getattr(pin.image, 'name', ''):
        pil = _pil_from_field_any(pin.image)
        if pil:
            sc = classify_pil_rgb_scores(pil)
            if sc:
                score_batches.append(sc)
    if getattr(pin, 'story_video', None) and getattr(pin.story_video, 'name', ''):
        for fr in _video_rgb_frames(pin.story_video):
            sc = classify_pil_rgb_scores(fr)
            if sc:
                score_batches.append(sc)

    if not score_batches:
        return None

    agg: dict[str, float] = {}
    keys = {'porn', 'hentai', 'sexy', 'drawing', 'neutral'}
    for k in keys:
        agg[k] = max((s.get(k, 0.0) for s in score_batches), default=0.0)

    return policy_from_scores(verified_adult, agg)


_MSG_MINOR = (
    'Ce média dépasse le seuil défini pour les comptes mineurs ou non vérifiés. '
    'Les contenus très suggestifs nécessitent un compte adulte avec date de naissance renseignée.'
)


def apply_server_visual_moderation_to_pin(pin, profile) -> None:
    """Met à jour ``media_sensitive_blur`` et ``needs_review`` après classification."""
    from .visibility import profile_is_verified_adult

    adult = profile_is_verified_adult(profile)
    try:
        decision = classify_pin_visual(pin, adult)
    except Exception as exc:
        logger.warning('Modération visuelle ignorée (erreur) : %s', exc)
        return

    if decision is None:
        return

    if decision.minor_reject:
        raise drf_serializers.ValidationError({'non_field_errors': [_MSG_MINOR]})

    blur = bool(getattr(pin, 'media_sensitive_blur', False) or decision.force_blur)
    needs = bool(decision.needs_staff_review)

    from .models import Pin

    Pin.objects.filter(pk=pin.pk).update(
        media_sensitive_blur=blur,
        needs_review=needs,
    )
    pin.media_sensitive_blur = blur
    pin.needs_review = needs
