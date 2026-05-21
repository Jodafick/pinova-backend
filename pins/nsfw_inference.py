"""Inférence NSFW ONNX côté serveur (facultatif : sans modèle, aucune décision automatique).

Configurez soit ``NSFW_ONNX_MODEL_PATH`` (fichier .onnx local), soit ``NSFW_ONNX_MODEL_URL`` (téléchargement vers le cache média).

``NSFW_ONNX_CLASSES`` = libellés des sorties du modèle, **dans le même ordre** que les probabilités
(ex. par défaut celui du modèle Mobilenet/nsfw-js : Drawing,Hentai,Neutral,Porn,Sexy).

Pour les modèles **binaire** Safe/NSFW (2 sorties), laisser deux libellés ex. Neutral,Unsafe et le code en déduit porn/hentai/sexy approximatif pour les seuils.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)
_LOCK = Lock()
_SESSION = None


def _cache_dir():
    from django.conf import settings

    root = getattr(settings, 'MEDIA_ROOT', None) or ''
    base = Path(str(root)) if root else Path('/tmp')
    p = base / '_pinova_model_cache'
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolved_onnx_model_path() -> Path | None:
    from django.conf import settings

    raw = (getattr(settings, 'NSFW_ONNX_MODEL_PATH', None) or '').strip()
    if raw:
        p = Path(raw)
        if p.exists():
            return p
        logger.warning('NSFW ONNX : fichier introuvable (%s)', p)
    url = (getattr(settings, 'NSFW_ONNX_MODEL_URL', None) or '').strip()
    if not url:
        return None
    dest = _cache_dir() / 'nsfw_classifier.onnx'
    try:
        if not dest.exists() or dest.stat().st_size < 1024:
            logger.info('Téléchargement du modèle NSFW ONNX vers %s', dest)
            urllib.request.urlretrieve(url, dest)  # noqa: S310 — URL contrôlée par l’opérateur
    except Exception as exc:
        logger.warning('Échec téléchargement modèle NSFW : %s', exc)
        return None
    return dest


def _get_session():
    global _SESSION
    with _LOCK:
        if _SESSION is False:
            return None
        if _SESSION is not None:
            return _SESSION
        path = resolved_onnx_model_path()
        if not path:
            logger.info('NSFW ONNX : pas de NSFW_ONNX_MODEL_PATH ni NSFW_ONNX_MODEL_URL.')
            _SESSION = False
            return None
        try:
            import onnxruntime as ort

            _SESSION = ort.InferenceSession(str(path), providers=['CPUExecutionProvider'])
        except Exception as exc:
            logger.warning('Chargement ONNX échoué : %s', exc)
            _SESSION = False
            return None
        return _SESSION


def _softmax_flat(z: np.ndarray) -> np.ndarray:
    zz = np.array(z).astype(np.float64).flatten()
    if zz.size == 0:
        return zz
    zz -= np.max(zz)
    ex = np.exp(zz)
    return ex / ex.sum()


def _prepare_tensor(pil_rgb: Image.Image) -> dict[str, Any]:
    """Prétraitement simple NCHW ou NHWC, taille carrée NSFW_ONNX_IMG_SIZE."""
    from django.conf import settings

    sess = _get_session()
    if sess is None:
        raise RuntimeError('no session')
    inp = sess.get_inputs()[0]
    name = inp.name
    layout = (getattr(settings, 'NSFW_ONNX_LAYOUT', 'NCHW') or 'NCHW').strip().upper()
    if layout not in ('NCHW', 'NHWC'):
        layout = 'NCHW'
    size = max(32, int(getattr(settings, 'NSFW_ONNX_IMG_SIZE', 224) or 224))
    imagenet = str(getattr(settings, 'NSFW_ONNX_NORMALIZE', 'imagenet')).lower() != 'scaled'
    img = pil_rgb.convert('RGB').resize((size, size), Image.Resampling.BILINEAR)
    arr = np.asarray(img).astype(np.float32) / 255.0
    if imagenet:
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
    if layout == 'NHWC':
        x = np.expand_dims(arr.astype(np.float32), 0)
    else:
        x = np.transpose(arr, (2, 0, 1))[np.newaxis].astype(np.float32)
    return {name: x}


def run_nsfw_probabilities_rgb(pil_rgb: Image.Image) -> np.ndarray | None:
    sess = _get_session()
    if sess is None:
        return None
    try:
        feed = _prepare_tensor(pil_rgb)
        outs = sess.run(None, feed)
    except Exception as exc:
        logger.warning('Inférence NSFW ONNX échec %s', exc)
        return None
    if not outs:
        return None
    raw = np.array(outs[0]).flatten()
    if raw.size == 2 and (raw.sum() <= 1.005 and raw.sum() >= 0.995):
        return raw.astype(np.float64)
    return _softmax_flat(raw.astype(np.float64))


def probs_to_scores(probs: np.ndarray) -> dict[str, float]:
    from django.conf import settings

    p = probs.astype(np.float64).flatten()
    raw = getattr(settings, 'NSFW_ONNX_CLASSES', '').strip()
    labels = (
        ['drawing', 'hentai', 'neutral', 'porn', 'sexy']
        if not raw
        else [s.strip().lower() for s in raw.split(',') if s.strip()]
    )
    n = len(labels)
    if p.size <= 0:
        return {'drawing': 0.0, 'hentai': 0.0, 'neutral': 1.0, 'porn': 0.0, 'sexy': 0.0}
    if p.size >= n > 1:
        m = dict(zip(labels, p[:n].tolist()))

        def g(*names: str, default=0.0):
            for nm in names:
                if nm in m:
                    return float(m[nm])
            return default

        return {
            'drawing': float(g('drawing', 'drawings')),
            'hentai': float(g('hentai')),
            'neutral': float(g('neutral', 'safe')),
            'porn': float(g('porn', 'pornography')),
            'sexy': float(g('sexy', 'suggestive')),
        }
    if p.size == 2:
        safe, unsafe = float(p[0]), float(p[1])
        bump = float(getattr(settings, 'NSFW_TWOCLASS_UNSAFE_BIAS', 0.0))
        unsafe = max(0.0, min(1.0, unsafe + bump))
        return {
            'drawing': safe * 0.75,
            'hentai': unsafe * 0.22,
            'neutral': safe * (1 - 0.75 * 0.3),
            'porn': unsafe * 0.58,
            'sexy': unsafe * 0.32,
        }
    # fallback multiclass générique sans labels utilisables
    return {
        'drawing': float(p[0]),
        'hentai': float(p[1]) if p.size > 3 else float(p[max(1, p.size - 2)]),
        'neutral': float(np.mean(p)),
        'porn': float(p[min(p.size - 1, 3)]) if p.size > 3 else float(p[max(2, p.size - 3)]),
        'sexy': float(p[min(p.size - 1, 4)]) if p.size > 4 else float(p[-1]),
    }


def classify_pil_rgb_scores(pil_rgb: Image.Image) -> dict[str, float] | None:
    probs = run_nsfw_probabilities_rgb(pil_rgb)
    if probs is None:
        return None
    try:
        return probs_to_scores(probs)
    except Exception as exc:
        logger.warning('NSFW probs→scores erreur %s', exc)
        return None
