"""
Seed complet pour développement / démo Fotoce.

Usage :
  python seed_data.py
  python scripts/seed_data.py

Variables d'environnement optionnelles :
  SEED_SUPERUSER_USERNAME / SEED_SUPERUSER_EMAIL / SEED_SUPERUSER_PASSWORD
  SEED_PIN_COUNT          — nombre de fotos « catalogue » (défaut 420 ; 120 sur Render)
  SEED_SKIP_NETWORK=1     — pas de téléchargement distant ; placeholders PNG colorés (Pillow).
                              Activé par défaut sur Render (variable RENDER=true). En local : SEED_SKIP_NETWORK=0.
  SEED_FORCE_NETWORK=1    — force le téléchargement d’images même sur Render (utile si le cache est préchauffé).
  SEED_IMAGE_CACHE_DIR    — dossier cache disque des images téléchargées (défaut : .seed_image_cache/).

  David Anato (david1anato) : la vague « fans » (followers, likes, FotoViewEvent) est toujours exécutée
  après création des fotos ; volumes modérés pour le dev (voir constantes SEED_DAVID_FAN_* en tête de
  seed_david_fan_army dans ce fichier).

  Images avec réseau : Picsum (IDs stables — nature, personnes, paysages) ; avatars profil = portraits Picsum.
  Miniatures feed générées automatiquement pour chaque foto catalogue (hors stories).

Les utilisateurs de test ont le mot de passe : password123

Modèles couverts (création ou nettoyage) : User ; Profile ; EmailOTP ; SubscriptionPricing ;
FotoceSubscriptionConfig ; SubscriptionPayment ; SubscriptionSeatInvitation ; SubscriptionSeatMember ;
SupportTicket ; UserBlock ; Notification ; PushSubscription ; Topic ; TopicTranslation ; LegalDocument ; FaqItem ;
Hashtag ; Board ; BoardCollaborationInvite ; Foto ; FotoVariant ; FotoBoard ; Save ; Like ; Comment ;
CommentLike ; ContentReport ; PrivatePinTag ; FotoProvenanceEvent ; FotoViewEvent ; SearchInteraction ;
ExpoPushToken (jeton factice mobile, idempotent par user id).
Stories : finalisation alignée sur `fotos/active-stories` (éphémères + `story_expires_at` futur).
Concours parrainage : `ReferrerReferralScore` + `ReferralLeaderboardEvent` (scores ≥ seuil API).
Monétisation : `BoostPackage` ; `PartnerCampaign` (pubs fil + ciblage) ; `FotoPromoCampaign` (campagnes créateur) ;
`FotoBoost` (pins boostés actifs / expirés).
Préférences pub sur `Profile` : `ad_ads_enabled`, `partner_ads_enabled` (selon plan).

Noms aléatoires (fans seed, etc.) : Faker (fr_FR) lorsque le paquet est installé.
"""
from __future__ import annotations

import hashlib
import io
import os
import random
from decimal import Decimal
import secrets
import base64
import uuid
import logging
from datetime import timedelta, date
from pathlib import Path
import re
from urllib.parse import quote

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import django

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fotoce_backend.settings')
django.setup()

import django.utils.timezone as dj_tz
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.temp import NamedTemporaryFile

from django.db import transaction

from accounts.models import (
    EmailOTP,
    FotoceSubscriptionConfig,
    Profile,
    SubscriptionPayment,
    SubscriptionPricing,
    SubscriptionSeatInvitation,
    SubscriptionSeatMember,
    SupportTicket,
    UserBlock,
)
from accounts.subscription_seats import generate_invite_plain_token_and_hash, grant_member_seat
from notifications.models import ExpoPushToken, Notification, PushSubscription
from contests.models import (
    ContestInteractionEvent,
    ContestResult,
    ContestSettings,
    CreatorContestScore,
    LeaderboardEvent,
    LeaderboardSnapshot,
    FotoContestScore,
)
from referrals.models import ReferralContestSettings, ReferralLeaderboardEvent, ReferrerReferralScore
from monetization.models import (
    BoostPackage,
    CreatorWallet,
    PartnerCampaign,
    FotoBoost,
    FotoPromoCampaign,
    TipPlatformConfig,
    TipTransaction,
    TipWithdrawal,
)
from monetization.tip_services import approve_tip_payment, get_or_create_wallet, split_tip_amount, tip_config
from referrals.referral_contest_cache import invalidate_referral_leaderboard_cache
from referrals.services import MIN_REFERRAL_LEADERBOARD_SCORE
from contests.services import (
    create_monthly_contest_if_missing,
    estimate_contest_adjusted_score_from_counts,
    get_foto_contest_display_counts,
)
from fotos.serializers import extract_mentions
from fotos.media_variants import ensure_foto_feed_thumbnail
from fotos.models import (
    Board,
    BoardCollaborationInvite,
    Comment,
    CommentLike,
    ContentReport,
    Hashtag,
    LegalDocument,
    FaqItem,
    Like,
    Foto,
    FotoBoard,
    FotoProvenanceEvent,
    FotoVariant,
    FotoViewEvent,
    PrivatePinTag,
    Save,
    SearchInteraction,
    Topic,
    TopicTranslation,
)

try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None


TOPIC_ICONS = [
    'home',
    'restaurant',
    'flight',
    'palette',
    'brush',
    'park',
    'checkroom',
    'self_improvement',
    'photo_camera',
    'construction',
    'computer',
    'sports_esports',
    'business_center',
    'payments',
    'school',
    'rocket_launch',
]

TOPIC_COLORS = [
    '#F59E0B',
    '#10B981',
    '#3B82F6',
    '#8B5CF6',
    '#EC4899',
    '#84CC16',
    '#06B6D4',
    '#EF4444',
    '#6366F1',
    '#14B8A6',
    '#F97316',
    '#22C55E',
]

PROFILE_DEMO_TRAITS: dict[str, dict] = {
    'clara': {
        'country_code': 'SN',
        'gender': 'woman',
        'city': 'Dakar',
        'preferred_currency': 'XOF',
        'interests': ['déco', 'design', 'mode'],
        'hobbies': ['photographie', 'voyage'],
        'birth_date': date(1993, 4, 12),
    },
    'leo': {
        'country_code': 'FR',
        'gender': 'man',
        'city': 'Paris',
        'preferred_currency': 'EUR',
        'interests': ['tech', 'design'],
        'hobbies': ['gaming', 'lecture'],
        'birth_date': date(1998, 9, 3),
    },
    'aya': {
        'country_code': 'CI',
        'gender': 'woman',
        'city': 'Abidjan',
        'preferred_currency': 'XOF',
        'interests': ['cuisine', 'voyage'],
        'hobbies': ['cuisine', 'yoga'],
        'birth_date': date(2001, 1, 20),
    },
    'max': {
        'country_code': 'BJ',
        'gender': 'man',
        'city': 'Cotonou',
        'preferred_currency': 'XOF',
        'interests': ['architecture', 'photo'],
        'hobbies': ['photographie', 'randonnée'],
        'birth_date': date(1990, 7, 8),
    },
    'zoe': {
        'country_code': 'FR',
        'gender': 'woman',
        'city': 'Lyon',
        'preferred_currency': 'EUR',
        'interests': ['mode', 'voyage'],
        'hobbies': ['couture'],
        'birth_date': date(1996, 11, 30),
    },
    'nina': {
        'country_code': 'TG',
        'gender': 'woman',
        'city': 'Lomé',
        'preferred_currency': 'XOF',
        'interests': ['écologie', 'jardinage'],
        'hobbies': ['jardinage'],
        'birth_date': date(2003, 5, 14),
    },
    'emma': {
        'country_code': 'GH',
        'gender': 'woman',
        'city': 'Accra',
        'preferred_currency': 'XOF',
        'interests': ['voyage', 'photo'],
        'hobbies': ['photographie'],
        'birth_date': date(1994, 8, 22),
    },
    'karim': {
        'country_code': 'ML',
        'gender': 'man',
        'city': 'Bamako',
        'preferred_currency': 'XOF',
        'interests': ['sport', 'musique'],
        'hobbies': ['football'],
        'birth_date': date(1999, 2, 2),
    },
    'sofia': {
        'country_code': 'SN',
        'gender': 'woman',
        'city': 'Saint-Louis',
        'preferred_currency': 'XOF',
        'interests': ['déco', 'voyage'],
        'hobbies': ['bricolage'],
        'birth_date': date(1997, 6, 18),
    },
    'lucas': {
        'country_code': 'FR',
        'gender': 'man',
        'city': 'Marseille',
        'preferred_currency': 'EUR',
        'interests': ['sport', 'tech'],
        'hobbies': ['gaming'],
        'birth_date': date(2000, 12, 5),
    },
    'david1anato': {
        'country_code': 'BJ',
        'gender': 'man',
        'city': 'Cotonou',
        'preferred_currency': 'XOF',
        'interests': ['design', 'photo', 'voyage'],
        'hobbies': ['photographie', 'randonnée'],
        'birth_date': date(1995, 6, 15),
    },
}

USER_SPECS = [
    # (Prénom affiché, plan)
    ('Clara', Profile.PLAN_PRO),
    ('Leo', Profile.PLAN_PLUS),
    ('Aya', Profile.PLAN_FREE),
    ('Max', Profile.PLAN_PRO),
    ('Zoe', Profile.PLAN_PLUS),
    ('Nina', Profile.PLAN_FREE),
    ('Emma', Profile.PLAN_PRO),
    ('Karim', Profile.PLAN_FREE),
    ('Sofia', Profile.PLAN_PLUS),
    ('Lucas', Profile.PLAN_FREE),
]

# Couleurs avatar CSS (HEX) — complètent les classes Tailwind pour tester le front.
HEX_AVATAR_POOL = [
    '#6366F1',
    '#EC4899',
    '#14B8A6',
    '#F97316',
    '#8B5CF6',
    '#0D9488',
    '#DB2777',
    '#CA8A04',
    '#059669',
]

HASHTAG_POOL = [
    'fotoce',
    'inspiration',
    'design',
    'daily',
    'creative',
    'art',
    'photo',
    'travel',
    'food',
    'wellness',
    'architecture',
    'minimal',
    'color',
    'story',
]

COMMENT_SNIPPETS_FR = [
    'Magnifique composition !',
    'Merci pour l’inspo 🔥',
    'Les couleurs sont parfaites.',
    'Tu as une source pour ça ?',
    'Ajouté à mes favoris.',
    'Incroyable travail.',
    'Le cadrage est nickel.',
    'Ça donne envie d’y être.',
    'Texture / lumière au top.',
    'J’adore l’ambiance.',
    'Référence enregistrée pour plus tard.',
    'Plutôt audacieux, ça marche.',
    'Le contraste fonctionne super bien.',
    'Simple et efficace.',
    'Merci pour le partage 🙏',
    'On sent le travail derrière.',
]

COMMENT_REPLY_SNIPPETS_FR = [
    'Totalement d’accord 👍',
    'Exactement mon ressenti.',
    'Oui, surtout au niveau des tons.',
    '😍 pareil !',
    '+1, bien vu.',
]
def ensure_superuser():
    username = os.environ.get('SEED_SUPERUSER_USERNAME', 'admin')
    email = os.environ.get('SEED_SUPERUSER_EMAIL', 'admin@example.com')
    password = os.environ.get('SEED_SUPERUSER_PASSWORD', 'admin1234')

    superuser, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email},
    )
    if created:
        superuser.email = email
        superuser.is_staff = True
        superuser.is_superuser = True
        superuser.set_password(password)
        superuser.save()
        logger.info(f"Superuser '{username}' créé.")
        return superuser

    if superuser.email != email:
        superuser.email = email
    if not superuser.is_staff:
        superuser.is_staff = True
    if not superuser.is_superuser:
        superuser.is_superuser = True

    superuser.set_password(password)
    superuser.save()
    logger.info(f"Superuser '{username}' mis à jour.")
    return superuser


def download_image(url: str):
    """Compat : télécharge sans exposer le type MIME."""
    tmp, _ext = download_image_to_temp(url)
    return tmp


def download_image_to_temp(url: str):
    """GET ; retourne (tempfile | None, extension : jpg, png, webp, gif)."""
    if requests is None:
        return None, None
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={'User-Agent': 'FotoceSeed/1.2 (+https://fotoce.invalid/seed)', 'Accept': 'image/*'},
            allow_redirects=True,
        )
        if response.status_code != 200:
            return None, None
        body = response.content or b''
        if len(body) < 900:
            return None, None
        ctype = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        ext = {
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/png': 'png',
            'image/webp': 'webp',
            'image/gif': 'gif',
        }.get(ctype)
        if not ext:
            path_low = url.split('?', 1)[0].lower()
            for marker, e in (
                ('.webp', 'webp'),
                ('.png', 'png'),
                ('.gif', 'gif'),
                ('.jpeg', 'jpg'),
                ('.jpg', 'jpg'),
            ):
                if path_low.endswith(marker):
                    ext = e
                    break
            else:
                ext = 'jpg'
        img_temp = NamedTemporaryFile(suffix='.' + ext)
        img_temp.write(body)
        img_temp.flush()
        return img_temp, ext
    except Exception:
        pass
    return None, None


# Compteurs téléchargements vs placeholders (résumé en fin de seed).
SEED_IMAGE_STATS: dict[str, int] = {
    'pin_remote': 0,
    'pin_placeholder': 0,
    'pin_feed_thumb': 0,
    'avatar_remote': 0,
    'campaign_remote': 0,
    'campaign_placeholder': 0,
}

# IDs Picsum stables — photos réelles (nature, personnes, paysages). Pas d’avatars illustrés.
IMAGE_THEME_PICSUM_IDS: dict[str, tuple[int, ...]] = {
    'architecture': (104, 158, 239, 417, 237),
    'food': (292, 312, 326, 431, 312),
    'japan': (317, 250, 349, 338),
    'workspace': (180, 366, 201, 0),
    'tattoo': (177, 399, 64, 65),
    'plants': (10, 16, 18, 28),
    'baking': (312, 326, 292),
    'streetwear': (64, 119, 177, 91),
    'yoga': (429, 447, 338, 28),
    'colors': (274, 275, 366, 180),
    'paris': (236, 338, 250, 104),
    'macrame': (96, 97, 108, 16),
    'nature': (10, 11, 28, 29, 37, 38, 43, 15),
    'design': (180, 201, 366, 158),
    'art': (62, 82, 429, 213),
    'decor': (158, 167, 108, 104),
    'kitchen': (292, 312, 326),
    'beach': (167, 168, 169, 29),
    'mountain': (15, 29, 43, 11),
    'city': (0, 1, 237, 250, 119),
    'portrait': (64, 65, 91, 177, 213, 338, 399, 429),
    'neon': (274, 366, 180, 237),
    'coffee': (30, 60, 312, 292),
}

# Portraits Picsum pour avatars profil (vraies photos, pas Dicebear).
AVATAR_PICSUM_PORTRAIT_IDS: tuple[int, ...] = (
    64, 65, 91, 177, 213, 338, 399, 429, 582, 659, 668, 837, 1011, 1012, 1025, 1027,
)

# Pool général si le thème ne matche pas.
REAL_PHOTO_PICSUM_IDS: tuple[int, ...] = (
    10, 11, 15, 16, 18, 28, 29, 37, 43, 64, 65, 91, 104, 119, 158, 177, 213, 237, 250,
    292, 312, 317, 326, 338, 366, 399, 417, 429, 431,
)

_IMAGE_THEME_RE = re.compile(
    r'_(architecture|food|japan|workspace|tattoo|plants|baking|streetwear|yoga|colors|'
    r'paris|macrame|nature|design|art|decor|kitchen|beach|mountain|city|portrait|neon|coffee)(?:_|$)'
)

# Portrait / paysage / carré, tailles mobiles et bannières.
SEED_IMAGE_DIMENSIONS: list[tuple[int, int]] = [
    (600, 900),
    (900, 600),
    (720, 1280),
    (1280, 720),
    (800, 800),
    (1080, 1080),
    (480, 720),
    (720, 480),
    (640, 960),
    (960, 640),
    (1024, 768),
    (768, 1024),
    (640, 1136),
    (1200, 675),
    (413, 531),
]


def _safe_seed_slug(key: str, max_len: int = 56) -> str:
    s = re.sub(r'[^a-zA-Z0-9_-]', '_', str(key)).strip('_')
    if not s:
        s = 'fotoce'
    return s[:max_len]


def _extract_image_theme(seed_key: str) -> str | None:
    m = _IMAGE_THEME_RE.search(str(seed_key))
    if m:
        return m.group(1)
    for theme in IMAGE_THEME_PICSUM_IDS:
        if theme in str(seed_key):
            return theme
    return None


def candidate_seed_image_urls(seed_key: str, width: int, height: int) -> list[str]:
    """Photos réelles Picsum (nature, personnes, paysages) — pas d’illustrations ni placeholders."""
    theme = _extract_image_theme(seed_key)
    digest = abs(hash(str(seed_key)))
    curated: list[str] = []
    if theme and theme in IMAGE_THEME_PICSUM_IDS:
        ids = IMAGE_THEME_PICSUM_IDS[theme]
        primary_id = ids[digest % len(ids)]
        curated.append(f'https://picsum.photos/id/{primary_id}/{width}/{height}')
        for pid in ids:
            if pid != primary_id:
                curated.append(f'https://picsum.photos/id/{pid}/{width}/{height}')
    pool_ids = REAL_PHOTO_PICSUM_IDS
    start = digest % len(pool_ids)
    for offset in range(min(8, len(pool_ids))):
        pid = pool_ids[(start + offset) % len(pool_ids)]
        url = f'https://picsum.photos/id/{pid}/{width}/{height}'
        if url not in curated:
            curated.append(url)
    return curated


def candidate_avatar_urls(username: str) -> list[str]:
    """Portraits photo réels (Picsum) — un ID stable par utilisateur."""
    digest = abs(hash(_safe_seed_slug(username, 48)))
    primary = AVATAR_PICSUM_PORTRAIT_IDS[digest % len(AVATAR_PICSUM_PORTRAIT_IDS)]
    alt = AVATAR_PICSUM_PORTRAIT_IDS[(digest + 3) % len(AVATAR_PICSUM_PORTRAIT_IDS)]
    return [
        f'https://picsum.photos/id/{primary}/400/400',
        f'https://picsum.photos/id/{primary}/256/256',
        f'https://picsum.photos/id/{alt}/400/400',
    ]


def seed_image_cache_dir() -> Path:
    raw = os.environ.get('SEED_IMAGE_CACHE_DIR', '').strip()
    cache = Path(raw) if raw else ROOT / '.seed_image_cache'
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _seed_cache_path(seed_key: str, ext: str) -> Path:
    digest = hashlib.sha256(str(seed_key).encode('utf-8')).hexdigest()[:24]
    return seed_image_cache_dir() / f'{digest}.{ext}'


def read_cached_seed_image(seed_key: str):
    for ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        path = _seed_cache_path(seed_key, ext if ext != 'jpeg' else 'jpg')
        if not path.is_file():
            continue
        try:
            if path.stat().st_size < 900:
                continue
            tmp = NamedTemporaryFile(suffix='.' + (ext if ext != 'jpeg' else 'jpg'))
            tmp.write(path.read_bytes())
            tmp.flush()
            fname = f'{_safe_seed_slug(seed_key, 52)}.{ext if ext != "jpeg" else "jpg"}'
            return tmp, fname
        except OSError:
            continue
    return None, None


def write_cached_seed_image(seed_key: str, tmp, ext: str) -> None:
    if not tmp:
        return
    try:
        tmp.seek(0)
        data = tmp.read()
        tmp.seek(0)
        if len(data) < 900:
            return
        path = _seed_cache_path(seed_key, ext)
        path.write_bytes(data)
    except OSError:
        pass


def fetch_seed_image_file(seed_key: str, skip_network: bool, tries: int = 14):
    """Cache disque + jusqu’à `tries` URLs (photos Picsum / Wikimedia en priorité)."""
    w, h = random.choice(SEED_IMAGE_DIMENSIONS)
    if skip_network:
        return None, f'{_safe_seed_slug(seed_key, 52)}.png'
    cached, cached_name = read_cached_seed_image(seed_key)
    if cached:
        return cached, cached_name
    urls = candidate_seed_image_urls(seed_key, w, h)
    for url in urls[: max(tries, 1)]:
        tmp, ext = download_image_to_temp(url)
        if tmp:
            write_cached_seed_image(seed_key, tmp, ext or 'jpg')
            return tmp, f'{_safe_seed_slug(seed_key, 52)}.{ext or "jpg"}'
    logger.warning('Aucune image distante pour %s (%s essais) — placeholder local.', seed_key, tries)
    return None, 'seed_failed.jpg'


def fetch_avatar_image_file(username: str, skip_network: bool):
    if skip_network:
        return None, None
    cache_key = f'avatar_{username}'
    cached, cached_name = read_cached_seed_image(cache_key)
    if cached:
        return cached, cached_name
    for url in candidate_avatar_urls(username):
        tmp, ext = download_image_to_temp(url)
        if tmp:
            write_cached_seed_image(cache_key, tmp, ext or 'jpg')
            return tmp, f'{_safe_seed_slug(username, 40)}.{ext or "jpg"}'
    logger.warning('Avatar distant indisponible pour %s — avatar_color conservé.', username)
    return None, None


def attach_profile_avatar(profile: Profile, username: str, skip_network: bool) -> None:
    tmp, fname = fetch_avatar_image_file(username, skip_network)
    if not tmp or not fname:
        return
    if profile.avatar:
        profile.avatar.delete(save=False)
    profile.avatar.save(fname, File(tmp), save=True)
    SEED_IMAGE_STATS['avatar_remote'] += 1


def render_seed_placeholder_png(seed: str, width: int = 640, height: int = 960) -> bytes:
    """PNG coloré (dégradé) — bien plus lisible qu’un pixel 1×1."""
    w = max(64, int(width))
    h = max(64, int(height))
    if Image is not None and ImageDraw is not None:
        try:
            digest = abs(hash(str(seed)))
            r1, g1, b1 = (digest >> 16) & 0xFF, (digest >> 8) & 0xFF, digest & 0xFF
            r2, g2, b2 = (r1 + 96) % 256, (g1 + 48) % 256, (b1 + 128) % 256
            img = Image.new('RGB', (w, h), (r1, g1, b1))
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, w, h // 2], fill=(r2, g2, b2))
            draw.rectangle([w // 8, h // 3, w - w // 8, h - h // 4], fill=(r1, g1, b1))
            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            return buf.getvalue()
        except Exception:
            pass
    return bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
        '0000000a49444154789c6300010000050001790000000049454e44ae426082'
    )


def placeholder_png_bytes(seed: str = 'fotoce', width: int = 640, height: int = 960) -> bytes:
    """Image PNG valide pour mode hors réseau (taille réaliste)."""
    return render_seed_placeholder_png(seed, width, height)


def seed_placeholder_content(seed: str, width: int | None = None, height: int | None = None) -> ContentFile:
    if width is None or height is None:
        w, h = SEED_IMAGE_DIMENSIONS[abs(hash(str(seed))) % len(SEED_IMAGE_DIMENSIONS)]
    else:
        w, h = width, height
    return ContentFile(render_seed_placeholder_png(seed, w, h))


def cleanup_existing_foto_media():
    logger.info('Suppression des médias fotos / variants / commentaires…')
    for v in FotoVariant.objects.iterator():
        if v.image:
            v.image.delete(save=False)
    FotoVariant.objects.all().delete()

    for c in Comment.objects.exclude(media='').iterator():
        if c.media:
            c.media.delete(save=False)

    for foto in Foto.objects.exclude(image='').iterator():
        if foto.image:
            foto.image.delete(save=False)

    pins_dir = Path(settings.MEDIA_ROOT) / 'fotos'
    if pins_dir.exists():
        for file_path in pins_dir.rglob('*'):
            if file_path.is_file():
                file_path.unlink(missing_ok=True)

    Foto.objects.all().delete()
    Hashtag.objects.all().delete()


def cleanup_relational_data():
    """Notifications, interactions, boards (orphelins), etc."""
    logger.info('Nettoyage des données relationnelles…')
    Notification.objects.all().delete()
    PushSubscription.objects.all().delete()
    SubscriptionPayment.objects.all().delete()
    SupportTicket.objects.all().delete()
    EmailOTP.objects.all().delete()

    ContentReport.objects.all().delete()
    BoardCollaborationInvite.objects.all().delete()
    UserBlock.objects.all().delete()
    SubscriptionSeatMember.objects.all().delete()
    SubscriptionSeatInvitation.objects.all().delete()

    CommentLike.objects.all().delete()
    Comment.objects.all().delete()
    Save.objects.all().delete()
    Like.objects.all().delete()
    FotoViewEvent.objects.all().delete()
    SearchInteraction.objects.all().delete()
    FotoProvenanceEvent.objects.all().delete()
    PrivatePinTag.objects.all().delete()
    FotoBoard.objects.all().delete()

    Board.collaborators.through.objects.all().delete()
    Board.objects.all().delete()

    TopicTranslation.objects.all().delete()
    ContestResult.objects.all().delete()
    LeaderboardSnapshot.objects.all().delete()
    LeaderboardEvent.objects.all().delete()
    CreatorContestScore.objects.all().delete()
    FotoContestScore.objects.all().delete()
    ContestInteractionEvent.objects.all().delete()
    ContestSettings.objects.all().delete()

    TipWithdrawal.objects.all().delete()
    TipTransaction.objects.all().delete()
    CreatorWallet.objects.all().delete()
    FotoBoost.objects.all().delete()
    FotoPromoCampaign.objects.all().delete()
    PartnerCampaign.objects.all().delete()


def seed_boost_packages() -> None:
    """Catalogue boost + campagnes (valeurs de démo ; en prod les tarifs se gèrent dans l’admin Django)."""
    catalog = [
        ('24h', 'Boost 24 h', BoostPackage.KIND_BOOST, 24, 1500),
        ('72h', 'Boost 3 jours', BoostPackage.KIND_BOOST, 72, 3500),
        ('7d', 'Boost 7 jours', BoostPackage.KIND_BOOST, 168, 7500),
        ('campaign-24h', 'Campagne 24 h', BoostPackage.KIND_CAMPAIGN, 24, 2500),
        ('campaign-72h', 'Campagne 3 jours', BoostPackage.KIND_CAMPAIGN, 72, 5500),
        ('campaign-7d', 'Campagne 7 jours', BoostPackage.KIND_CAMPAIGN, 168, 11500),
    ]
    for slug, label, package_kind, hours, amount in catalog:
        BoostPackage.objects.update_or_create(
            slug=slug,
            defaults={
                'label': label,
                'package_kind': package_kind,
                'duration_hours': hours,
                'amount': amount,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )
    logger.info('BoostPackage (boost + campagnes) à jour.')


def attach_partner_campaign_image(campaign: PartnerCampaign, seed_key: str, skip_network: bool) -> None:
    temp_img, fname = fetch_seed_image_file(seed_key, skip_network)
    try:
        if temp_img:
            campaign.image.save(fname or f'{seed_key}.jpg', File(temp_img), save=True)
            SEED_IMAGE_STATS['campaign_remote'] += 1
        elif skip_network:
            campaign.image.save(
                f'{seed_key}.png',
                seed_placeholder_content(seed_key),
                save=True,
            )
            SEED_IMAGE_STATS['campaign_placeholder'] += 1
    finally:
        if temp_img:
            temp_img.close()


def seed_partner_campaigns(admin: User, topics_by_name: dict[str, Topic], skip_network: bool) -> None:
    """Campagnes partenaire visibles dans les fils (démo)."""
    now = dj_tz.now()
    frontend = str(getattr(settings, 'FRONTEND_URL', '') or 'http://localhost:5174').rstrip('/')
    specs = [
        {
            'title': 'Fotoce Plus — printemps créatif',
            'body': 'Passez en Plus : moins de pubs réseau, tags privés illimités et boards collaboratifs.',
            'sponsor_name': 'Fotoce',
            'cta_label': 'Voir les offres',
            'cta_url': f'{frontend}/premium',
            'topic_slug': '',
            'priority': 30,
            'impressions': 240,
            'clicks': 19,
            'seed_key': 'partner_fotoce_plus',
        },
        {
            'title': 'Atelier déco — mobilier afro-contemporain',
            'body': 'Nouvelle collection limitée : textiles, lampes et accessoires faits main.',
            'sponsor_name': 'Atelier Kente Home',
            'cta_label': 'Découvrir',
            'cta_url': 'https://example.com/kente-home',
            'topic_slug': 'Maison et déco',
            'targeting': {
                'countries': ['SN', 'BJ', 'CI'],
                'languages': ['fr'],
                'interests': ['déco', 'design'],
                'topics': ['maison et déco'],
            },
            'priority': 22,
            'impressions': 88,
            'clicks': 6,
            'seed_key': 'partner_deco',
        },
        {
            'title': 'Voyages — circuits Afrique de l’Ouest',
            'body': 'Dakar, Accra, Lomé : petits groupes, guides locaux, départs toute l’année.',
            'sponsor_name': 'Teranga Routes',
            'cta_label': 'Réserver',
            'cta_url': 'https://example.com/teranga-routes',
            'topic_slug': 'Voyages',
            'targeting': {
                'countries': ['SN', 'FR', 'GH'],
                'languages': ['fr', 'en'],
                'topics': ['voyages'],
                'age_min': 22,
                'age_max': 45,
                'interests': ['voyage'],
            },
            'priority': 20,
            'impressions': 64,
            'clicks': 4,
            'seed_key': 'partner_travel',
        },
        {
            'title': 'Campagne expirée (seed)',
            'body': 'Ne doit pas apparaître dans le fil.',
            'sponsor_name': 'Archive',
            'cta_label': 'Lien',
            'cta_url': 'https://example.com/expired',
            'topic_slug': '',
            'priority': 5,
            'impressions': 400,
            'clicks': 0,
            'is_active': True,
            'ends_at': now - timedelta(days=2),
            'seed_key': 'partner_expired',
        },
        {
            'title': 'Campagne désactivée (seed)',
            'body': 'is_active=False — test admin.',
            'sponsor_name': 'Off',
            'cta_label': '—',
            'cta_url': 'https://example.com/off',
            'topic_slug': '',
            'priority': 1,
            'is_active': False,
            'seed_key': 'partner_inactive',
        },
    ]
    for row in specs:
        topic_slug = row['topic_slug']
        if topic_slug and topic_slug not in topics_by_name:
            topic_slug = ''
        campaign, created = PartnerCampaign.objects.update_or_create(
            title=row['title'],
            defaults={
                'body': row['body'],
                'sponsor_name': row['sponsor_name'],
                'cta_label': row['cta_label'],
                'cta_url': row['cta_url'],
                'topic_slug': topic_slug,
                'targeting': row.get('targeting', {}),
                'priority': row['priority'],
                'is_active': row.get('is_active', True),
                'starts_at': row.get('starts_at', now - timedelta(days=7)),
                'ends_at': row.get('ends_at', now + timedelta(days=60)),
                'impressions': row.get('impressions', 0),
                'clicks': row.get('clicks', 0),
                'created_by': admin,
            },
        )
        if created or not campaign.image:
            attach_partner_campaign_image(campaign, row['seed_key'], skip_network)
    logger.info('PartnerCampaign : %d campagnes seed.', PartnerCampaign.objects.filter(is_active=True).count())


def _david_public_fotos(public_fotos: list[Foto], limit: int = 16) -> list[Foto]:
    """Pins publics non-story de david1anato (boosts + promos liées)."""
    david = User.objects.filter(username='david1anato').first()
    if not david:
        return []
    return [
        p
        for p in public_fotos
        if p.author_id == david.id and not p.is_story and p.visibility == Foto.VISIBILITY_PUBLIC
    ][:limit]


def seed_david_foto_boosts(public_fotos: list[Foto]) -> int:
    """Boosts actifs / expirés / en attente pour david1anato."""
    pkg_24 = BoostPackage.objects.filter(slug='24h', is_active=True).first()
    pkg_72 = BoostPackage.objects.filter(slug='72h', is_active=True).first()
    pkg_7d = BoostPackage.objects.filter(slug='7d', is_active=True).first()
    if not pkg_24:
        logger.warning('Boosts David ignorés (BoostPackage 24h absent).')
        return 0

    david = User.objects.filter(username='david1anato').first()
    if not david:
        return 0

    david_pins = _david_public_fotos(public_fotos, limit=20)
    if not david_pins:
        logger.warning('Boosts David ignorés (aucun foto public).')
        return 0

    now = dj_tz.now()
    boosts_created = 0
    boost_specs: list[tuple[int, BoostPackage, str, timedelta, timedelta]] = [
        (0, pkg_24, FotoBoost.STATUS_ACTIVE, timedelta(hours=5), timedelta(hours=19)),
        (1, pkg_24, FotoBoost.STATUS_ACTIVE, timedelta(hours=2), timedelta(hours=22)),
        (2, pkg_72, FotoBoost.STATUS_ACTIVE, timedelta(hours=8), timedelta(hours=64)),
        (3, pkg_24, FotoBoost.STATUS_ACTIVE, timedelta(hours=1), timedelta(hours=23)),
        (4, pkg_7d or pkg_72, FotoBoost.STATUS_ACTIVE, timedelta(days=1), timedelta(days=6)),
        (5, pkg_24, FotoBoost.STATUS_ACTIVE, timedelta(hours=12), timedelta(hours=12)),
        (6, pkg_72, FotoBoost.STATUS_EXPIRED, timedelta(days=5), timedelta(days=2)),
        (7, pkg_24, FotoBoost.STATUS_EXPIRED, timedelta(days=3), timedelta(days=2)),
        (8, pkg_24, FotoBoost.STATUS_PENDING, timedelta(hours=0), timedelta(hours=24)),
    ]
    for foto_idx, package, status, started_ago, ends_in in boost_specs:
        if foto_idx >= len(david_pins):
            break
        if package is None:
            continue
        FotoBoost.objects.create(
            foto=david_pins[foto_idx],
            owner=david,
            package=package,
            status=status,
            starts_at=now - started_ago,
            ends_at=now + ends_in if status == FotoBoost.STATUS_ACTIVE else now - ends_in,
            fedapay_transaction_id=f'seed_boost_david_{foto_idx}_{uuid.uuid4().hex[:12]}',
        )
        boosts_created += 1

    logger.info('David — FotoBoost : %d entrées (actifs, expirés, pending).', boosts_created)
    return boosts_created


def seed_foto_boosts(public_fotos: list[Foto]) -> None:
    """Pins boostés pour tester badge fil + ranking discover."""
    boosts_created = seed_david_foto_boosts(public_fotos)

    pkg_24 = BoostPackage.objects.filter(slug='24h', is_active=True).first()
    if not pkg_24:
        if boosts_created == 0:
            logger.warning('FotoBoost seed ignoré (BoostPackage 24h absent).')
        return

    now = dj_tz.now()

    def _foto_candidates(username: str, limit: int = 6) -> list[Foto]:
        author = User.objects.filter(username=username).first()
        if not author:
            return []
        return [
            p
            for p in public_fotos
            if p.author_id == author.id and not p.is_story and p.visibility == Foto.VISIBILITY_PUBLIC
        ][:limit]

    for uname in ('clara', 'max', 'emma'):
        author = User.objects.filter(username=uname).first()
        if not author:
            continue
        pins_u = _foto_candidates(uname, 2)
        if not pins_u:
            continue
        FotoBoost.objects.create(
            foto=pins_u[0],
            owner=author,
            package=pkg_24,
            status=FotoBoost.STATUS_ACTIVE,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=23),
        )
        boosts_created += 1

    logger.info('FotoBoost : %d entrées seed (David + autres créateurs).', boosts_created)


def attach_creator_campaign_media(campaign: FotoPromoCampaign, seed_key: str, skip_network: bool) -> None:
    temp_img, fname = fetch_seed_image_file(seed_key, skip_network)
    try:
        if temp_img:
            campaign.media.save(fname or f'{seed_key}.jpg', File(temp_img), save=False)
            campaign.media_type = FotoPromoCampaign.MEDIA_IMAGE
            campaign.save(update_fields=['media', 'media_type', 'updated_at'])
            SEED_IMAGE_STATS['campaign_remote'] += 1
        elif skip_network:
            campaign.media.save(
                f'{seed_key}.png',
                seed_placeholder_content(seed_key),
                save=False,
            )
            campaign.media_type = FotoPromoCampaign.MEDIA_IMAGE
            campaign.save(update_fields=['media', 'media_type', 'updated_at'])
            SEED_IMAGE_STATS['campaign_placeholder'] += 1
        else:
            campaign.media.save(
                f'{seed_key}_fallback.png',
                seed_placeholder_content(seed_key),
                save=False,
            )
            campaign.media_type = FotoPromoCampaign.MEDIA_IMAGE
            campaign.save(update_fields=['media', 'media_type', 'updated_at'])
            SEED_IMAGE_STATS['campaign_placeholder'] += 1
    finally:
        if temp_img:
            temp_img.close()


def seed_foto_promo_campaigns(
    david: User | None,
    public_fotos: list[Foto],
    topics_by_name: dict[str, Topic],
    skip_network: bool,
) -> None:
    """Campagnes publicitaires créateur David (autonomes + liées à des fotos)."""
    if not david:
        return
    pkg = BoostPackage.objects.filter(slug='72h', is_active=True).first()
    pkg_7d = BoostPackage.objects.filter(slug='7d', is_active=True).first()
    if not pkg:
        pkg = BoostPackage.objects.filter(is_active=True).first()
    if not pkg:
        logger.warning('FotoPromoCampaign seed ignoré (aucun BoostPackage).')
        return

    david_pins = _david_public_fotos(public_fotos, limit=12)
    now = dj_tz.now()
    frontend = str(getattr(settings, 'FRONTEND_URL', '') or 'http://localhost:5174').rstrip('/')
    deco_topic = 'Maison et déco'
    travel_topic = 'Voyages'
    photo_topic = 'Photographie'
    design_topic = 'Inspiration design'
    specs = [
        {
            'headline': 'Studio David — presets Lightroom Afrique',
            'body': 'Pack de 12 presets pour paysages et portraits, optimisé mobile.',
            'cta_label': 'Acheter',
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': deco_topic if deco_topic in topics_by_name else '',
            'targeting': {
                'countries': ['BJ', 'SN', 'CI'],
                'languages': ['fr'],
                'plans': ['free', 'plus'],
                'interests': ['photo', 'design'],
                'age_min': 18,
                'age_max': 40,
            },
            'impressions': 156,
            'clicks': 11,
            'pin_views': 420,
            'seed_key': 'creator_david_presets',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Shoot Cotonou — série urbaine 2026',
            'body': 'Nouvelle série photo : rues, textures et portraits au golden hour.',
            'cta_label': 'Voir la série',
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': photo_topic if photo_topic in topics_by_name else '',
            'targeting': {
                'countries': ['BJ', 'TG', 'SN'],
                'languages': ['fr'],
                'interests': ['photo', 'voyage'],
                'genders': ['woman', 'man'],
            },
            'impressions': 312,
            'clicks': 28,
            'pin_views': 890,
            'pin_index': 0,
            'seed_key': 'creator_david_cotonou',
            'package': pkg_7d or pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Portfolio David — UI/UX & photo',
            'body': 'Découvrez mes dernières créations : interfaces, moodboards et shootings.',
            'cta_label': 'Explorer',
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': design_topic if design_topic in topics_by_name else '',
            'targeting': {
                'countries': ['BJ', 'FR', 'CI'],
                'languages': ['fr', 'en'],
                'plans': ['free', 'plus', 'pro'],
                'interests': ['design', 'photo'],
            },
            'impressions': 245,
            'clicks': 19,
            'pin_views': 610,
            'pin_index': 2,
            'seed_key': 'creator_david_portfolio',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Atelier voyage — carnets créatifs',
            'body': 'Carnets illustrés pour créateurs en déplacement en Afrique de l’Ouest.',
            'cta_label': 'Découvrir',
            'cta_url': 'https://example.com/carnets-voyage',
            'topic_slug': travel_topic if travel_topic in topics_by_name else '',
            'targeting': {
                'countries': ['SN', 'FR', 'GH'],
                'languages': ['fr'],
                'topics': [travel_topic.lower()] if travel_topic in topics_by_name else [],
                'interests': ['voyage'],
                'genders': ['woman', 'man'],
                'age_min': 20,
                'age_max': 50,
            },
            'impressions': 92,
            'clicks': 7,
            'pin_views': 180,
            'seed_key': 'creator_travel_notebooks',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Masterclass — retouche mobile Pro',
            'body': 'Session live : workflow Lightroom mobile + export pour Fotoce.',
            'cta_label': "S'inscrire",
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': photo_topic if photo_topic in topics_by_name else '',
            'targeting': {
                'countries': ['BJ', 'SN'],
                'languages': ['fr'],
                'plans': ['plus', 'pro'],
                'interests': ['photo'],
            },
            'impressions': 78,
            'clicks': 9,
            'pin_views': 95,
            'pin_index': 4,
            'seed_key': 'creator_david_masterclass',
            'package': pkg_7d or pkg,
            'status': FotoPromoCampaign.STATUS_PAUSED,
        },
        {
            'headline': 'Formation Pro — monétiser sa création',
            'body': 'Webinaire gratuit : boosts, campagnes et pourboires sur Fotoce.',
            'cta_label': "S'inscrire",
            'cta_url': f'{frontend}/premium',
            'topic_slug': '',
            'targeting': {
                'plans': ['pro'],
                'languages': ['fr'],
                'currencies': ['XOF', 'EUR'],
            },
            'impressions': 34,
            'clicks': 5,
            'pin_views': 42,
            'seed_key': 'creator_pro_webinar',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Textures Afrique — pack HD',
            'body': '50 textures haute résolution pour vos moodboards et mockups.',
            'cta_label': 'Télécharger',
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': design_topic if design_topic in topics_by_name else '',
            'targeting': {
                'countries': ['BJ', 'CI', 'GH', 'SN'],
                'languages': ['fr'],
                'interests': ['design', 'architecture'],
            },
            'impressions': 201,
            'clicks': 16,
            'pin_views': 340,
            'pin_index': 6,
            'seed_key': 'creator_david_textures',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_ACTIVE,
        },
        {
            'headline': 'Campagne expirée — soldes presets',
            'body': 'Offre terminée (seed) — ne doit plus apparaître dans le fil.',
            'cta_label': 'Archives',
            'cta_url': f'{frontend}/profile/david1anato',
            'topic_slug': '',
            'targeting': {'languages': ['fr']},
            'impressions': 500,
            'clicks': 40,
            'pin_views': 0,
            'seed_key': 'creator_david_expired',
            'package': pkg,
            'status': FotoPromoCampaign.STATUS_EXPIRED,
            'starts_at': now - timedelta(days=45),
            'ends_at': now - timedelta(days=5),
        },
    ]
    for idx, row in enumerate(specs):
        foto = None
        pin_index = row.get('pin_index')
        if pin_index is not None and pin_index < len(david_pins):
            foto = david_pins[pin_index]
        campaign, created = FotoPromoCampaign.objects.update_or_create(
            owner=david,
            headline=row['headline'],
            defaults={
                'body': row['body'],
                'cta_label': row['cta_label'],
                'cta_url': row['cta_url'],
                'topic_slug': row.get('topic_slug', ''),
                'targeting': row.get('targeting', {}),
                'package': row.get('package', pkg),
                'status': row.get('status', FotoPromoCampaign.STATUS_ACTIVE),
                'starts_at': row.get('starts_at', now - timedelta(days=2)),
                'ends_at': row.get('ends_at', now + timedelta(days=30)),
                'impressions': row.get('impressions', 0),
                'clicks': row.get('clicks', 0),
                'pin_views': row.get('pin_views', 0),
                'pin': foto,
                'fedapay_transaction_id': f'seed_promo_david_{idx}_{uuid.uuid4().hex[:12]}',
            },
        )
        if created or not campaign.media:
            attach_creator_campaign_media(campaign, row['seed_key'], skip_network)
    logger.info(
        'David — FotoPromoCampaign : %d campagnes actives, %d au total.',
        FotoPromoCampaign.objects.filter(owner=david, status=FotoPromoCampaign.STATUS_ACTIVE).count(),
        FotoPromoCampaign.objects.filter(owner=david).count(),
    )


def seed_profile_ad_preferences(profiles_by_username: dict[str, Profile]) -> None:
    """Préférences publicitaires démo : pubs actives pour tous les profils."""
    for profile in profiles_by_username.values():
        profile.ad_ads_enabled = True
        profile.partner_ads_enabled = True
        profile.save(update_fields=['ad_ads_enabled', 'partner_ads_enabled'])
    logger.info('Préférences publicitaires profils seed à jour.')


def seed_internal_tips(public_fotos: list[Foto]) -> None:
    """Portefeuilles et pourboires internes approuvés (démo)."""
    TipPlatformConfig.load()
    david = User.objects.filter(username='david1anato').first()
    clara = User.objects.filter(username='clara').first()
    max_user = User.objects.filter(username='max').first()
    if not david:
        return
    cfg = tip_config()
    wallet = get_or_create_wallet(david)
    wallet.payout_phone = '+22990123456'
    wallet.payout_label = 'Mobile Money'
    wallet.save(update_fields=['payout_phone', 'payout_label', 'updated_at'])

    donors = [u for u in (clara, max_user) if u]
    foto = next((p for p in public_fotos if p.author_id == david.id), None)
    amounts = [1000, 2500, 5000]
    for donor, amount in zip(donors, amounts[: len(donors)]):
        commission, net = split_tip_amount(amount, cfg.commission_percent)
        tip = TipTransaction.objects.create(
            donor=donor,
            recipient=david,
            foto=pin,
            amount_gross=amount,
            commission_amount=commission,
            amount_net=net,
            currency_iso=cfg.currency_iso,
            message='Merci pour ton travail !',
            fedapay_transaction_id=f'seed_tip_{donor.id}_{amount}',
            status=TipTransaction.STATUS_PENDING,
        )
        approve_tip_payment(tip)
    wallet.refresh_from_db()
    logger.info(
        'Pourboires internes seed : wallet david solde=%s %s.',
        wallet.balance_available,
        wallet.currency_iso,
    )


def seed_monetization(
    admin: User,
    public_fotos: list[Foto],
    topics_by_name: dict[str, Topic],
    profiles_by_username: dict[str, Profile],
    skip_network: bool,
) -> None:
    logger.info('Monétisation (boost, pubs partenaire, prefs pub, pourboires)…')
    seed_boost_packages()
    seed_profile_ad_preferences(profiles_by_username)
    seed_partner_campaigns(admin, topics_by_name, skip_network)
    seed_foto_boosts(public_fotos)
    david = User.objects.filter(username='david1anato').first()
    seed_foto_promo_campaigns(david, public_fotos, topics_by_name, skip_network)
    seed_internal_tips(public_fotos)


def seed_contest_data(public_fotos: list[Foto], regular_users: list[User]) -> None:
    """Données concours : settings actifs + scores dérivés des vrais likes / vues / saves / commentaires / partages."""
    logger.debug('seed_contest_data: %d utilisateurs seed (non utilisés pour le classement).', len(regular_users))
    if not public_fotos:
        logger.info('Contest seed ignoré (aucun foto public).')
        return

    contest = create_monthly_contest_if_missing()
    contest.is_active = True
    contest.auto_reset_enabled = True
    contest.max_winners = 3
    contest.distribution_mode = ContestSettings.DISTRIBUTION_PERCENTAGE
    contest.total_prize_pool = 10000
    contest.distribution_weights_json = [50, 30, 20]
    contest.weight_likes = 1.0
    contest.weight_views = 0.12
    contest.weight_shares = 2.8
    contest.weight_saves = 2.0
    contest.weight_comments = 2.3
    contest.leaderboard_refresh_interval = 3
    contest.websocket_broadcast_threshold = 0.15
    contest.save()
    # Referral contest settings (modèle séparé).
    ReferralContestSettings.objects.update_or_create(
        contest=contest,
        defaults={
            'defer_rewards': True,
            'min_account_age_hours': 12,
            'min_engagement_actions': 1,
            'reward_delay_hours': 1,
            'min_days_before_reward': 2,
            'max_signups_per_ip_per_24h': 40,
            'max_signups_per_device_per_24h': 20,
            'max_referrals_per_referrer_per_24h': 40,
            'referee_trust_threshold': 0.25,
            'min_pins_published': 0,
        },
    )

    non_story_public = [p for p in public_fotos if not p.is_story]
    eligible = [p for p in non_story_public if contest.start_at <= p.created_at < contest.end_at]
    if not eligible:
        eligible = non_story_public[: min(120, len(non_story_public))]

    ranked: list[tuple[Foto, float, dict[str, int]]] = []
    for foto in eligible:
        counts = get_foto_contest_display_counts(foto)
        score = estimate_contest_adjusted_score_from_counts(contest, foto, counts)
        ranked.append((foto, score, counts))

    ranked.sort(key=lambda row: (-row[1], row[0].pk))
    chosen_tuples = ranked[: min(120, len(ranked))]
    pin_scores_created = []
    creator_totals: dict[int, float] = {}

    for rank, (foto, score, counts) in enumerate(chosen_tuples, start=1):
        obj = FotoContestScore.objects.create(
            contest=contest,
            foto=foto,
            creator=foto.author,
            raw_score=score,
            adjusted_score=score,
            rank=rank,
            previous_rank=rank,
            total_likes=counts[ContestInteractionEvent.TYPE_LIKE],
            total_views=counts[ContestInteractionEvent.TYPE_VIEW],
            total_saves=counts[ContestInteractionEvent.TYPE_SAVE],
            total_shares=counts[ContestInteractionEvent.TYPE_SHARE],
            total_comments=counts[ContestInteractionEvent.TYPE_COMMENT],
        )
        pin_scores_created.append(obj)
        creator_totals[obj.creator_id] = creator_totals.get(obj.creator_id, 0.0) + obj.adjusted_score

    creator_rows = sorted(creator_totals.items(), key=lambda it: it[1], reverse=True)
    for rank, (creator_id, total) in enumerate(creator_rows, start=1):
        CreatorContestScore.objects.create(
            contest=contest,
            creator_id=creator_id,
            adjusted_score=round(total, 4),
            rank=rank,
            previous_rank=rank,
        )

    # Flux live initial pour web/mobile (valeurs cohérentes avec FotoContestScore).
    for row in pin_scores_created[:40]:
        likes = int(row.total_likes or 0)
        views = int(row.total_views or 0)
        shares = int(row.total_shares or 0)
        saves = int(row.total_saves or 0)
        comments = int(row.total_comments or 0)
        LeaderboardEvent.objects.create(
            contest=contest,
            event_type='pin_rank_updated',
            entity_type='pin',
            entity_id=row.foto_id,
            payload={
                'foto_id': row.foto_id,
                'foto_slug': row.foto.slug,
                'pin_title': row.foto.title,
                'creator_id': row.creator_id,
                'creator_username': row.creator.username,
                'contest_key': contest.contest_key,
                'score': row.adjusted_score,
                'rank': row.rank,
                'previous_rank': row.previous_rank,
                'delta_score': 0,
                'likes': likes,
                'views': views,
                'shares': shares,
                'saves': saves,
                'comments': comments,
                'engagement_total': likes + views + shares + saves + comments,
            },
        )

    top_creator_rows = CreatorContestScore.objects.filter(contest=contest).select_related('creator').order_by('rank')[:25]
    for row in top_creator_rows:
        LeaderboardEvent.objects.create(
            contest=contest,
            event_type='creator_rank_updated',
            entity_type='creator',
            entity_id=row.creator_id,
            payload={
                'creator_id': row.creator_id,
                'creator_username': row.creator.username,
                'contest_key': contest.contest_key,
                'score': row.adjusted_score,
                'rank': row.rank,
                'previous_rank': row.previous_rank,
            },
        )

    ordered_win = list(
        FotoContestScore.objects.filter(contest=contest, pin__is_story=False)
        .order_by('-adjusted_score', 'rank', 'foto_id')
        .select_related('creator')
    )
    winners = []
    seen_w = set()
    for row in ordered_win:
        if row.creator_id in seen_w:
            continue
        seen_w.add(row.creator_id)
        winners.append(row)
        if len(winners) >= contest.max_winners:
            break
    ContestResult.objects.update_or_create(
        contest=contest,
        defaults={
            'winners_json': [
                {
                    'rank': idx + 1,
                    'foto_id': row.foto_id,
                    'creator_id': row.creator_id,
                    'score': row.adjusted_score,
                }
                for idx, row in enumerate(winners)
            ],
            'payout_json': [
                {'rank': 1, 'amount': 5000},
                {'rank': 2, 'amount': 3000},
                {'rank': 3, 'amount': 2000},
            ],
        },
    )
    logger.info(
        f'Contest seed OK — {contest.contest_key}: '
        f'{FotoContestScore.objects.filter(contest=contest).count()} fotos, '
        f'{CreatorContestScore.objects.filter(contest=contest).count()} créateurs.'
    )

    seed_referral_contest_leaderboard(contest, regular_users)


def seed_referral_contest_leaderboard(contest, regular_users: list[User]) -> None:
    """
    Classement parrainage démo : scores ≥ MIN_REFERRAL_LEADERBOARD_SCORE pour apparaître dans l’API live.
    Émet aussi des événements `referrer_rank_updated` (polling HTTP / backlog WebSocket).
    """
    if not regular_users:
        logger.info('Referral contest seed ignoré (aucun utilisateur seed).')
        return

    preferred_order = [
        'david1anato',
        'clara',
        'max',
        'emma',
        'leo',
        'sofia',
        'karim',
        'lucas',
        'aya',
        'zoe',
        'nina',
    ]
    by_username = {u.username: u for u in regular_users}
    participants: list[User] = []
    for name in preferred_order:
        u = by_username.get(name)
        if u and u not in participants:
            participants.append(u)

    if not participants:
        return

    min_sc = float(MIN_REFERRAL_LEADERBOARD_SCORE)
    # Échelle décroissante, toutes les entrées visibles côté front
    base_scores = [520, 455, 402, 355, 310, 268, 232, 198, 170, 145, 125, 108]
    rows: list[tuple[User, float]] = []
    for i, user in enumerate(participants):
        if i < len(base_scores):
            sc = float(base_scores[i])
        else:
            sc = max(min_sc, 108.0 - (i - len(base_scores)) * 5.0)
        rows.append((user, sc))

    rows.sort(key=lambda r: (-r[1], r[0].pk))

    for rank, (user, total) in enumerate(rows, start=1):
        ReferrerReferralScore.objects.update_or_create(
            contest=contest,
            referrer=user,
            defaults={
                'total_score': total,
                'rank': rank,
                'previous_rank': rank,
            },
        )

    for rank, (user, total) in enumerate(rows, start=1):
        ReferralLeaderboardEvent.objects.create(
            contest=contest,
            event_type='referrer_rank_updated',
            entity_id=user.id,
            payload={
                'referrer_id': user.id,
                'username': user.username,
                'contest_key': contest.contest_key,
                'total_score': total,
                'rank': rank,
                'previous_rank': rank,
                'delta': 0.0,
            },
        )

    invalidate_referral_leaderboard_cache(contest.id)
    logger.info(
        'Referral contest seed OK — %s: %s parrains (seuil score %.0f).',
        contest.contest_key,
        len(rows),
        min_sc,
    )


def cleanup_seed():
    cleanup_relational_data()
    cleanup_existing_foto_media()


def seed_subscription_pricing():
    catalog = [
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_SOLO, 1500, 30),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_SOLO, 16200, 365),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_FAMILY, 4500, 30),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_FAMILY, 48600, 365),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_TEAM, 12000, 30),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_TEAM, 129600, 365),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_SOLO, 2500, 30),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_SOLO, 27000, 365),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_FAMILY, 7500, 30),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_FAMILY, 81000, 365),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_MONTHLY, SubscriptionPricing.SEAT_TEAM, 20000, 30),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_YEARLY, SubscriptionPricing.SEAT_TEAM, 216000, 365),
    ]
    for plan, cycle, seat_bundle, amount, days in catalog:
        SubscriptionPricing.objects.update_or_create(
            plan=plan,
            billing_cycle=cycle,
            seat_bundle=seat_bundle,
            defaults={
                'amount': amount,
                'duration_days': days,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )
    logger.info('Tarifs SubscriptionPricing à jour.')


def seed_fotoce_subscription_config():
    cfg = FotoceSubscriptionConfig.load()
    if cfg.annual_discount_percent != 12:
        cfg.annual_discount_percent = 12
        cfg.save(update_fields=['annual_discount_percent'])
    logger.info('FotoceSubscriptionConfig (singleton) à jour.')


def seed_legal_documents():
    """Pages légales + contact (alignées sur fotos.legal_defaults)."""
    from fotos.legal_defaults import (
        CONTACT_EN,
        CONTACT_FR,
        PRIVACY_EN,
        PRIVACY_FR,
        TERMS_EN,
        TERMS_FR,
        default_title,
    )

    LegalDocument.objects.update_or_create(
        slug=LegalDocument.SLUG_PRIVACY,
        defaults={
            'title_fr': default_title('privacy', 'fr'),
            'title_en': default_title('privacy', 'en'),
            'body_fr': PRIVACY_FR,
            'body_en': PRIVACY_EN,
            'contact_email': '',
            'translations_cache': {},
        },
    )
    LegalDocument.objects.update_or_create(
        slug=LegalDocument.SLUG_TERMS,
        defaults={
            'title_fr': default_title('terms', 'fr'),
            'title_en': default_title('terms', 'en'),
            'body_fr': TERMS_FR,
            'body_en': TERMS_EN,
            'contact_email': '',
            'translations_cache': {},
        },
    )
    LegalDocument.objects.update_or_create(
        slug=LegalDocument.SLUG_CONTACT,
        defaults={
            'title_fr': default_title('contact', 'fr'),
            'title_en': default_title('contact', 'en'),
            'body_fr': CONTACT_FR,
            'body_en': CONTACT_EN,
            'contact_email': 'support@fotoce.app',
            'translations_cache': {},
        },
    )
    logger.info('LegalDocument (privacy / terms / contact) à jour.')


def seed_faq_items():
    """Entrées FAQ par défaut (FR/EN), liées aux pages légales."""
    seeds = [
        {
            'sort_order': 10,
            'question_fr': 'Comment gérer la confidentialité de mon compte ?',
            'question_en': 'How do I manage my account privacy?',
            'answer_fr': (
                'Paramétrez la visibilité de vos fotos, la politique de commentaires et les informations '
                'affichées sur votre profil. Pour savoir quelles données nous traitons, consultez la '
                'politique de confidentialité.'
            ),
            'answer_en': (
                'Adjust foto visibility, comments policy, and profile information. '
                'See our Privacy Policy for details on data processing.'
            ),
            'related_legal_slug': LegalDocument.SLUG_PRIVACY,
        },
        {
            'sort_order': 20,
            'question_fr': 'Quelles sont les règles d’utilisation de la plateforme ?',
            'question_en': 'What are the platform rules?',
            'answer_fr': (
                'Fotoce attend un comportement respectueux des lois et de la communauté. Contenus interdits, '
                'comptes et responsabilités sont décrits dans les conditions d’utilisation.'
            ),
            'answer_en': (
                'Fotoce requires lawful, respectful behaviour. Prohibited content and account rules are '
                'described in our Terms of Service.'
            ),
            'related_legal_slug': LegalDocument.SLUG_TERMS,
        },
        {
            'sort_order': 30,
            'question_fr': 'Comment vous contacter ?',
            'question_en': 'How can I contact you?',
            'answer_fr': (
                'Pour une question commerciale, technique ou un signalement, écrivez-nous à l’adresse indiquée '
                'sur la page contact. Nous répondons en général sous quelques jours ouvrés.'
            ),
            'answer_en': (
                'For business, technical questions or reports, use the email shown on our contact page. '
                'We usually reply within a few business days.'
            ),
            'related_legal_slug': LegalDocument.SLUG_CONTACT,
        },
        {
            'sort_order': 40,
            'question_fr': 'Comment passer à Premium ou au dashboard créateur ?',
            'question_en': 'How do I upgrade to Premium or use the creator dashboard?',
            'answer_fr': (
                'Les offres Premium et les outils créateur sont disponibles depuis l’application ou le site. '
                'Les modalités d’abonnement et d’utilisation sont précisées dans les conditions d’utilisation.'
            ),
            'answer_en': (
                'Premium plans and creator tools are available in the app or on the website. '
                'Subscription terms are set out in our Terms of Service.'
            ),
            'related_legal_slug': LegalDocument.SLUG_TERMS,
        },
    ]
    for row in seeds:
        FaqItem.objects.update_or_create(
            question_fr=row['question_fr'],
            defaults={
                'question_en': row['question_en'],
                'answer_fr': row['answer_fr'],
                'answer_en': row['answer_en'],
                'sort_order': row['sort_order'],
                'is_published': True,
                'related_legal_slug': row['related_legal_slug'],
            },
        )
    logger.info('FaqItem (seed) à jour.')


def random_foto_content_flags() -> dict:
    """Politique commentaires + flags modération / sensible (échantillon)."""
    return {
        'comments_policy': random.choices(
            [Foto.COMMENTS_OPEN, Foto.COMMENTS_FOLLOWERS_ONLY, Foto.COMMENTS_CLOSED],
            weights=[0.88, 0.09, 0.03],
            k=1,
        )[0],
        'media_sensitive_blur': random.random() < 0.045,
        'moderation_hidden': random.random() < 0.008,
    }


def seed_board_collaboration_invite_sample(boards_by_user: dict[int, list[Board]]) -> None:
    """Invitation collab tableau (pending), distincte du M2M direct Leo/Clara."""
    clara = User.objects.filter(username='clara').first()
    nina = User.objects.filter(username='nina').first()
    if not clara or not nina or not boards_by_user.get(clara.id):
        return
    pub_board = next((b for b in boards_by_user[clara.id] if not b.is_private), None)
    if not pub_board:
        return
    BoardCollaborationInvite.objects.get_or_create(
        board=pub_board,
        invitee=nina,
        defaults={
            'invited_by': clara,
            'status': BoardCollaborationInvite.STATUS_PENDING,
        },
    )
    logger.info('BoardCollaborationInvite (pending) créée.')


def seed_foto_feed_thumbnails(created_fotos: list[Foto]) -> None:
    """Miniatures feed (max 400px) pour les fotos catalogue (hors stories)."""
    candidates = [
        p for p in created_fotos
        if not p.is_story and p.image and getattr(p.image, 'name', '')
    ]
    ok = 0
    for foto in candidates:
        try:
            foto.refresh_from_db()
            if ensure_foto_feed_thumbnail(pin, force=True):
                ok += 1
        except Exception as exc:
            logger.warning('Miniature feed seed foto=%s : %s', foto.pk, exc)
    logger.info('Miniatures feed fotos : %d/%d.', ok, len(candidates))


def seed_foto_variants_square_sample(created_fotos: list[Foto]) -> None:
    """Variantes carrées (hors story) pour tester les crops API / front."""
    candidates = [p for p in created_fotos if p.image and not p.is_story]
    random.shuffle(candidates)
    n = 0
    for foto in candidates[:14]:
        if FotoVariant.objects.filter(foto=pin, kind=FotoVariant.KIND_SQUARE).exists():
            continue
        try:
            foto.image.open('rb')
            raw = foto.image.read()
            foto.image.close()
        except Exception:
            continue
        suf = Path(pin.image.name).suffix.lower() if foto.image.name else '.jpg'
        if suf not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
            suf = '.jpg'
        pv = FotoVariant(foto=pin, kind=FotoVariant.KIND_SQUARE)
        pv.image.save(f'variant_sq_{pin.slug}{suf}', ContentFile(raw), save=True)
        n += 1
    logger.info(f'FotoVariant carré (seed) : {n} fichiers.')


def seed_content_sample_reports(public_fotos: list[Foto], regular_users: list[User]) -> None:
    """Signalements foto / profil / commentaire (contraintes uniques)."""
    if len(public_fotos) < 2 or len(regular_users) < 4:
        logger.info('ContentReport : ignoré (données insuffisantes).')
        return
    pin_a, pin_b = public_fotos[0], public_fotos[1]
    r0, r1, r2 = regular_users[0], regular_users[1], regular_users[2]
    target = next((u for u in regular_users if u.id not in (r0.id, r1.id, r2.id)), regular_users[3])

    ContentReport.objects.get_or_create(
        reporter=r0,
        foto=pin_a,
        defaults={'category': 'spam', 'details': 'Seed : signalement foto.', 'reason': ''},
    )
    ContentReport.objects.get_or_create(
        reporter=r1,
        reported_user=target,
        defaults={'category': 'harassment', 'details': 'Seed : signalement profil.', 'reason': ''},
    )
    c = Comment.objects.filter(foto=pin_b, parent__isnull=True).exclude(user=target).first()
    if c:
        ContentReport.objects.get_or_create(
            reporter=r2,
            comment=c,
            defaults={'category': 'other', 'details': 'Seed : signalement commentaire.', 'reason': ''},
        )
    logger.info('ContentReport (échantillon) créés.')


def seed_user_blocks_sample() -> None:
    lucas = User.objects.filter(username='lucas').first()
    karim = User.objects.filter(username='karim').first()
    if lucas and karim and lucas.id != karim.id:
        UserBlock.objects.get_or_create(blocker=lucas, blocked=karim)
        print('UserBlock (échantillon) créé.')


def seed_subscription_seat_hub_demo(owner: User, invitee_pending: User, sponsored_member: User) -> None:
    """Hub famille : un siège actif + invitation en attente (+ ligne refusée)."""
    zoe = User.objects.filter(username='zoe').first()
    with transaction.atomic():
        _plain, digest = generate_invite_plain_token_and_hash()
        SubscriptionSeatInvitation.objects.create(
            owner=owner,
            invitee=invitee_pending,
            token_hash=digest,
            status=SubscriptionSeatInvitation.STATUS_PENDING,
            expires_at=dj_tz.now() + timedelta(days=5),
        )
        grant_member_seat(owner, sponsored_member)
    if zoe:
        _p2, digest2 = generate_invite_plain_token_and_hash()
        SubscriptionSeatInvitation.objects.create(
            owner=owner,
            invitee=zoe,
            token_hash=digest2,
            status=SubscriptionSeatInvitation.STATUS_DECLINED,
            expires_at=dj_tz.now() + timedelta(days=3),
            responded_at=dj_tz.now() - timedelta(hours=2),
        )
    print('SubscriptionSeatInvitation / SubscriptionSeatMember (seed) OK.')


def seed_topic_translations(topics_by_name: dict[str, Topic]):
    samples = [
        (
            'Photographie',
            {'en': 'Photography', 'es': 'Fotografía', 'de': 'Fotografie'},
        ),
        (
            'Architecture moderne',
            {'en': 'Modern architecture', 'es': 'Arquitectura moderna'},
        ),
        ('Voyages', {'en': 'Travel', 'it': 'Viaggi'}),
        ('Mode', {'en': 'Fashion', 'pt': 'Moda'}),
    ]
    for name, translations in samples:
        if name not in topics_by_name:
            continue
        TopicTranslation.objects.update_or_create(
            topic=name,
            defaults={'translations': translations},
        )
    print('TopicTranslation (échantillon) créées.')


def finalize_seed_stories_for_active_ring(story_fotos: list[Foto]) -> None:
    """
    Aligne les stories seed avec l’API GET `fotos/active-stories` :
    - filtres : is_story, publication non planifiée dans le futur, story_expires_at non nul et > now ;
    - les stories « grille » (story_ephemeral=False) ont story_expires_at=None côté save() → exclues du bandeau ;
    - on force story_ephemeral=True + une expiration dans le futur, un created_at récent (UX),
      et on annule toute planification future qui masquerait encore le foto.

    (Sans ceci, expires tombe à NULL pour non-éphémère, ou avec des dates passées après recul de created_at.)
    """
    if not story_fotos:
        return
    now = dj_tz.now()
    n = 0
    for p in story_fotos:
        p.refresh_from_db()
        minutes_ago = random.randint(3, 220)
        created_at = now - timedelta(minutes=minutes_ago)
        expires = now + timedelta(hours=random.randint(10, 22))

        upd = {
            'created_at': created_at,
            'updated_at': now,
            'story_ephemeral': True,
            'story_expires_at': expires,
        }
        if p.scheduled_publish_at and p.scheduled_publish_at > now:
            upd['scheduled_publish_at'] = None

        Foto.objects.filter(pk=p.pk).update(**upd)
        n += 1
    logger.info(
        'Stories seed (%s) : story_ephemeral=True, story_expires_at dans 10–22 h, '
        'created_at récent, planif future retirée pour le bandeau active-stories.',
        n,
    )


# Vague « fans » david1anato — exécutée à chaque seed (ajuster ici pour stresser l’API en local).
SEED_DAVID_FAN_FOLLOWERS = 2000  # Augmenté pour tester la notation K/M
SEED_DAVID_FAN_VIEW_EVENTS = 1500000  # 1.5M vues pour tester la notation M
SEED_DAVID_FAN_LIKES_PER_FAN = 50
SEED_DAVID_FAN_FOLLOWERS_CAP = 1000000
SEED_DAVID_FAN_VIEW_EVENTS_CAP = 1000000000


def seed_david_fan_army(david_user: User) -> None:
    """
    Followers + likes + FotoViewEvent pour david1anato (compteurs API réels).

    Les volumes très élevés en une seule commande restent limités par les constantes ci-dessus
    (temps / disque / mémoire).
    """
    try:
        from faker import Faker
        from mimesis import Person
        from mimesis.locales import Locale
    except ImportError:
        logger.warning('seed_david_fan_army : Faker ou Mimesis manquant — pip install faker mimesis')
        return

    from django.contrib.auth.hashers import make_password

    cap_followers = SEED_DAVID_FAN_FOLLOWERS_CAP
    cap_views = SEED_DAVID_FAN_VIEW_EVENTS_CAP
    n_followers = max(0, min(int(SEED_DAVID_FAN_FOLLOWERS), cap_followers))
    n_views = max(0, min(int(SEED_DAVID_FAN_VIEW_EVENTS), cap_views))
    likes_per_fan = max(0, int(SEED_DAVID_FAN_LIKES_PER_FAN))

    if n_followers == 0 and n_views == 0 and likes_per_fan == 0:
        return

    fake = Faker('fr_FR')
    person = Person(Locale.FR)
    pw_hash = make_password('!seed_fan_inactive!')
    david_profile = Profile.objects.get(user_id=david_user.id)
    foto_ids = list(Foto.objects.filter(author=david_user).values_list('id', flat=True))
    if not foto_ids:
        logger.info('seed_david_fan_army : aucun foto David — skip.')
        return

    logger.info(
        f'seed_david_fan_army : followers={n_followers}, vues≈{n_views}, '
        f'likes/fan≤{likes_per_fan} (pins David={len(foto_ids)})…',
    )

    FollowingThrough = Profile.following.through
    user_batch_size = 1000
    fan_users: list[User] = []

    for batch_start in range(0, n_followers, user_batch_size):
        batch_end = min(batch_start + user_batch_size, n_followers)
        users_chunk: list[User] = []
        for j in range(batch_start, batch_end):
            uname = f'fan_{person.username(mask="l_l_d")}_{j:04d}_{secrets.token_hex(2)}'
            users_chunk.append(
                User(
                    username=uname[:150],
                    email=f'{uname}@seed.fotoce.invalid',
                    password=pw_hash,
                    is_active=True,
                )
            )
        User.objects.bulk_create(users_chunk, batch_size=user_batch_size)
        usernames = [u.username for u in users_chunk]
        id_by_name = dict(User.objects.filter(username__in=usernames).values_list('username', 'id'))
        resolved_chunk: list[User] = []
        for u in users_chunk:
            pk = id_by_name.get(u.username)
            if pk:
                u.pk = pk
                resolved_chunk.append(u)
        fan_users.extend(resolved_chunk)

        profiles_chunk: list[Profile] = []
        for u in resolved_chunk:
            display = person.full_name()[:255]
            profiles_chunk.append(
                Profile(
                    user=u,
                    display_name=display,
                    subscription_plan=Profile.PLAN_FREE,
                    preferred_language=random.choice(['fr', 'fr', 'en']),
                    discoverable_profile=True,
                    private_profile=False,
                )
            )
        Profile.objects.bulk_create(profiles_chunk, batch_size=user_batch_size)
        logger.info(f'  -> Créé {len(resolved_chunk)} utilisateurs/profils fans ({batch_end}/{n_followers})')

    if fan_users:
        logger.info('  -> Création des liens de follow...')
        fan_profile_ids = list(
            Profile.objects.filter(user_id__in=[u.id for u in fan_users]).values_list('id', flat=True)
        )
        follow_rows = [
            FollowingThrough(from_profile_id=pid, to_profile_id=david_profile.id)
            for pid in fan_profile_ids
        ]
        for i in range(0, len(follow_rows), 6000):
            FollowingThrough.objects.bulk_create(follow_rows[i : i + 6000], ignore_conflicts=True)
        logger.info(f'  -> {len(follow_rows)} follows créés.')

    fan_user_ids = [u.id for u in fan_users]
    if fan_user_ids and likes_per_fan > 0:
        logger.info('  -> Création des likes...')
        like_objs: list[Like] = []
        rng = random.Random(424242)
        for uid in fan_user_ids:
            k = min(likes_per_fan, len(foto_ids))
            if k <= 0:
                continue
            for pid in rng.sample(foto_ids, k=k):
                like_objs.append(Like(user_id=uid, foto_id=pid))
        for i in range(0, len(like_objs), 8000):
            Like.objects.bulk_create(like_objs[i : i + 8000], ignore_conflicts=True)
        logger.info(f'  -> {len(like_objs)} likes créés.')

    if fan_user_ids and n_views > 0:
        logger.info(f'  -> Génération de {n_views} vues (simulées via bulk)...')
        view_batch: list[FotoViewEvent] = []
        n_pins = len(foto_ids)
        n_fans = len(fan_user_ids)
        chunk_target = 25000
        total_views_created = 0
        for offset in range(0, n_views, chunk_target):
            view_batch.clear()
            limit = min(chunk_target, n_views - offset)
            for k in range(limit):
                view_batch.append(
                    FotoViewEvent(
                        user_id=fan_user_ids[(offset + k) % n_fans],
                        foto_id=foto_ids[(offset + k) % n_pins],
                    )
                )
            FotoViewEvent.objects.bulk_create(view_batch, batch_size=8000)
            total_views_created += limit
            if total_views_created % 100000 == 0 or total_views_created == n_views:
                logger.info(f'     - {total_views_created}/{n_views} vues...')

    david_profile.refresh_from_db()
    n_followers_david = david_profile.followers.count()
    logger.info(
        f'seed_david_fan_army : terminé — {len(fan_user_ids)} comptes fans créés, '
        f'followers David (API)≈{n_followers_david}, vues insérées≈{n_views}.',
    )


def attach_image_to_pin(foto: Foto, temp_img, fname: str, skip_network: bool) -> bool:
    stem = Path(fname).stem if fname else f'pin_{pin.pk}'
    if temp_img:
        foto.image.save(fname, File(temp_img), save=True)
        SEED_IMAGE_STATS['pin_remote'] += 1
    else:
        seed = str(pin.pk or foto.slug or stem)
        foto.image.save(
            f'{stem}.png',
            seed_placeholder_content(seed),
            save=True,
        )
        SEED_IMAGE_STATS['pin_placeholder'] += 1
    if not foto.is_story and foto.image and getattr(pin.image, 'name', ''):
        try:
            if ensure_foto_feed_thumbnail(pin, force=True):
                SEED_IMAGE_STATS['pin_feed_thumb'] += 1
        except Exception as exc:
            logger.warning('Miniature feed attach foto=%s : %s', foto.pk, exc)
    return True


def resolve_skip_network() -> bool:
    """Réseau off si SEED_SKIP_NETWORK ; SEED_FORCE_NETWORK=1 l’emporte sur Render."""
    if os.environ.get('SEED_FORCE_NETWORK', '').lower() in ('1', 'true', 'yes'):
        return False
    return os.environ.get('SEED_SKIP_NETWORK', '').lower() in ('1', 'true', 'yes')


def _apply_deploy_defaults() -> None:
    """Sur Render : seed sans téléchargement d'images et volume fotos modéré (sauf SEED_FORCE_NETWORK)."""
    on_render = os.environ.get('RENDER', '').lower() in ('true', '1', 'yes')
    if not on_render:
        return
    if os.environ.get('SEED_FORCE_NETWORK', '').lower() not in ('1', 'true', 'yes'):
        os.environ.setdefault('SEED_SKIP_NETWORK', '1')
    os.environ.setdefault('SEED_PIN_COUNT', '120')


def seed_data():
    _apply_deploy_defaults()
    for key in SEED_IMAGE_STATS:
        SEED_IMAGE_STATS[key] = 0
    logger.info('Mise à jour complète de la base de données (seed)…')
    skip_network = resolve_skip_network()
    pin_target = int(os.environ.get('SEED_PIN_COUNT', '420'))

    cleanup_seed()

    admin = ensure_superuser()
    User.objects.exclude(is_superuser=True).delete()

    seed_subscription_pricing()
    seed_fotoce_subscription_config()
    seed_legal_documents()
    seed_faq_items()

    users: list[User] = [admin]
    profiles_by_username: dict[str, Profile] = {}

    logger.info('Création des utilisateurs et profils…')
    try:
        from faker import Faker as _FakerForBios

        _fb = _FakerForBios('fr_FR')
        _fb.seed_instance(9000 + pin_target)
        bios = [
            (_fb.sentence(nb_words=random.randint(4, 10))).replace('.', '').strip() + '.'
            for _ in range(10)
        ]
    except ImportError:
        bios = [
            'Designer & curieux.',
            'Photos du quotidien.',
            'Minimalisme et voyages.',
            'Creative coder.',
            '',
            'Fan de street art.',
        ]
    for idx, (display_name, plan) in enumerate(USER_SPECS):
        uname = display_name.lower()
        user = User.objects.create_user(
            username=uname,
            email=f'{uname}@example.com',
            password='password123',
        )
        profile: Profile = user.profile
        profile.display_name = display_name
        profile.subscription_plan = plan
        profile.bio = random.choice(bios)
        tw_avatar_colors = [
            'bg-amber-400',
            'bg-emerald-400',
            'bg-rose-400',
            'bg-sky-400',
            'bg-indigo-400',
            'bg-lime-400',
            'bg-orange-400',
            'bg-teal-400',
            'bg-violet-400',
            'bg-fuchsia-400',
            'bg-pink-400',
        ]
        profile.avatar_color = random.choice(HEX_AVATAR_POOL) if idx % 2 == 0 else random.choice(tw_avatar_colors)
        profile.discoverable_profile = True
        profile.preferred_language = random.choice(['fr', 'fr', 'en'])
        profile.notifications_recommendations = idx % 3 == 0
        profile.notifications_followers = True
        profile.notifications_saves = True
        if plan == Profile.PLAN_PRO:
            profile.translation_quota_monthly = 5000
            profile.tips_enabled = random.choice([True, False])
            profile.tips_url = ''
            profile.subscription_renewal_at = dj_tz.now() + timedelta(days=20)
        elif plan == Profile.PLAN_PLUS:
            profile.translation_quota_monthly = 200
            profile.subscription_renewal_at = dj_tz.now() + timedelta(days=12)
        else:
            profile.translation_quota_monthly = 5

        # Un profil privé pour tester les règles de visibilité
        if uname == 'nina':
            profile.private_profile = True
        traits = PROFILE_DEMO_TRAITS.get(uname, {})
        if traits:
            profile.country_code = traits.get('country_code', profile.country_code)
            profile.gender = traits.get('gender', profile.gender)
            profile.city = traits.get('city', profile.city)
            profile.preferred_currency = traits.get('preferred_currency', profile.preferred_currency)
            profile.interests = traits.get('interests', profile.interests or [])
            profile.hobbies = traits.get('hobbies', profile.hobbies or [])
            if traits.get('birth_date'):
                profile.birth_date = traits['birth_date']
        profile.save()
        attach_profile_avatar(profile, uname, skip_network)
        profiles_by_username[uname] = profile
        users.append(user)

    david_user = User.objects.create_user(
        username='david1anato',
        email='david1anato@gmail.com',
        password='password123',
    )
    dprof: Profile = david_user.profile
    dprof.display_name = 'David Anato'
    dprof.subscription_plan = Profile.PLAN_PRO
    dprof.bio = 'Créateur Fotoce — design, photo & voyage.'
    dprof.avatar_color = '#e11d48'
    dprof.subscription_seat_bundle = 'family'
    dprof.discoverable_profile = True
    dprof.preferred_language = 'fr'
    dprof.translation_quota_monthly = 5000
    dprof.subscription_renewal_at = dj_tz.now() + timedelta(days=25)
    dprof.private_profile = False
    david_traits = PROFILE_DEMO_TRAITS.get('david1anato', {})
    dprof.country_code = david_traits.get('country_code', 'BJ')
    dprof.gender = david_traits.get('gender', 'man')
    dprof.city = david_traits.get('city', 'Cotonou')
    dprof.preferred_currency = david_traits.get('preferred_currency', 'XOF')
    dprof.interests = david_traits.get('interests', ['design', 'photo', 'voyage'])
    dprof.hobbies = david_traits.get('hobbies', ['photographie'])
    dprof.birth_date = david_traits.get('birth_date', date(1995, 6, 15))
    dprof.tips_enabled = True
    dprof.tips_url = ''
    dprof.save()
    attach_profile_avatar(dprof, 'david1anato', skip_network)
    profiles_by_username['david1anato'] = dprof
    users.append(david_user)

    # Admin peut commenter dans le seed ; même clé que pour les autres utilisateurs.
    profiles_by_username[admin.username] = admin.profile

    # Graphe de follows (pas symétrique)
    regular_users = [u for u in users if not u.is_superuser]
    for u in regular_users:
        others = [x for x in regular_users if x.id != u.id]
        for f in random.sample(others, k=min(4, len(others))):
            u.profile.following.add(f.profile)

    DAVID_BOARDS = [
        ('Inspirations studio', False),
        ('Photos — Afrique', False),
        ('Privé — clients', True),
        ('Moodboard UI/UX', False),
        ('Voyages 2026', False),
        ('Textures & matières', False),
        ('Food & recettes', False),
        ('Architecture', False),
        ('Street & urbain', False),
        ('Références perso', True),
    ]

    logger.info('Création des boards…')
    boards_by_user: dict[int, list[Board]] = {}
    board_names = [
        ('Inspirations 2026', False),
        ('Privé — repaires', True),
        ('Moodboard voyage', False),
        ('Réfs design', False),
    ]
    for u in regular_users:
        boards_by_user[u.id] = []
        board_pairs = DAVID_BOARDS if u.username == 'david1anato' else board_names[: random.randint(2, 4)]
        for bname, is_priv in board_pairs:
            b, _ = Board.objects.get_or_create(
                user=u,
                name=bname,
                defaults={
                    'description': f'Tableau de {u.username}',
                    'is_private': is_priv,
                },
            )
            boards_by_user[u.id].append(b)
    # Collaborateurs : Leo collabore sur un board public de Clara
    clara = User.objects.filter(username='clara').first()
    leo = User.objects.filter(username='leo').first()
    if clara and leo and boards_by_user.get(clara.id):
        pub_board = next((b for b in boards_by_user[clara.id] if not b.is_private), None)
        if pub_board:
            pub_board.collaborators.add(leo)

    seed_board_collaboration_invite_sample(boards_by_user)

    topic_names = [
        'Maison et déco',
        'Recettes faciles',
        'Voyages',
        'Inspiration design',
        'Art & illustration',
        'Plantes',
        'Mode',
        'Bien-être',
        'Photographie',
        'DIY & Crafts',
        'Technologie',
        'Gaming setup',
        'Business',
        'Finance perso',
        'Éducation',
        'Productivité',
        'Architecture moderne',
        'Street art',
        'Cuisine africaine',
        'Cuisine asiatique',
        'Desserts',
        'Pâtisserie',
        'Fitness',
        'Yoga',
        'Méditation',
        'Santé',
        'Beauté',
        'Coiffure',
        'Mariage',
        'Bébé & famille',
        'Animaux',
        'Nature',
        'Sports',
        'Football',
        'Basketball',
        'Musique',
        'Cinéma',
        'Séries',
        'Lecture',
        'Poésie',
        'Science',
        'Astronomie',
        'Automobile',
        'Moto',
        'Cyclisme',
        'Immobilier',
        'Minimalisme',
        'Rénovation',
        'Jardinage',
        'Écologie',
    ]
    topics_catalog = [
        {
            'name': name,
            'icon': TOPIC_ICONS[index % len(TOPIC_ICONS)],
            'color': TOPIC_COLORS[index % len(TOPIC_COLORS)],
        }
        for index, name in enumerate(topic_names)
    ]
    topics_by_name: dict[str, Topic] = {}
    for topic_data in topics_catalog:
        topic_obj, _ = Topic.objects.get_or_create(name=topic_data['name'])
        updates = []
        if topic_obj.icon != topic_data['icon']:
            topic_obj.icon = topic_data['icon']
            updates.append('icon')
        if topic_obj.color != topic_data['color']:
            topic_obj.color = topic_data['color']
            updates.append('color')
        if updates:
            topic_obj.save(update_fields=updates)
        topics_by_name[topic_data['name']] = topic_obj

    seed_topic_translations(topics_by_name)

    image_queries = [
        'architecture',
        'food',
        'japan',
        'workspace',
        'tattoo',
        'plants',
        'baking',
        'streetwear',
        'yoga',
        'colors',
        'paris',
        'macrame',
        'nature',
        'design',
        'art',
        'decor',
        'kitchen',
        'beach',
        'mountain',
        'city',
        'portrait',
        'neon',
        'coffee',
    ]

    created_fotos: list[Foto] = []
    story_fotos: list[Foto] = []

    logger.info(f'Création de ~{pin_target} fotos — multi-sources JPG/PNG/WebP/GIF, dimensions variées (stories free/plus/pro)…')

    def maybe_visibility(u: User, topic_obj: Topic) -> str:
        pr = profiles_by_username[u.username]
        if pr.private_profile and random.random() < 0.25:
            return Foto.VISIBILITY_FOLLOWERS
        roll = random.random()
        if roll < 0.82:
            return Foto.VISIBILITY_PUBLIC
        if roll < 0.94:
            return Foto.VISIBILITY_FOLLOWERS
        return Foto.VISIBILITY_PRIVATE

    for i in range(100, 100 + pin_target):
        query = random.choice(image_queries)
        topic = random.choice(topic_names)
        topic_obj = topics_by_name[topic]
        temp_img, media_fname = fetch_seed_image_file(f'pin{i}_{query}', skip_network)

        author = random.choice(regular_users)
        vis = maybe_visibility(author, topic_obj)

        # Stories : odds plus élevées pour utilisateurs Plus/Pro sans les exclure des Free
        pr = profiles_by_username[author.username]
        story_weight = {'free': 0.06, 'plus': 0.16, 'pro': 0.22}[pr.subscription_plan]
        is_story = random.random() < story_weight

        # Pas de publication planifiée pour les stories : sinon exclues du bandeau active-stories.
        scheduled = None
        if (
            (not is_story)
            and pr.subscription_plan == Profile.PLAN_PRO
            and random.random() < 0.04
        ):
            scheduled = dj_tz.now() + timedelta(days=random.randint(1, 14))

        foto = Foto.objects.create(
            title=f"Inspiration {query.capitalize()} {i + 1}",
            description=f"Découverte sur le thème {query} — {topic}. #seed",
            author=author,
            topic=topic_obj,
            visibility=vis,
            link=f'https://example.com/ref/{i}' if random.random() < 0.15 else '',
            is_story=is_story,
            scheduled_publish_at=scheduled,
            **random_foto_content_flags(),
        )

        if attach_image_to_pin(pin, temp_img, media_fname, skip_network):
            foto.refresh_from_db()

        # Hashtags (sous-ensemble)
        if random.random() < 0.35:
            for hn in random.sample(HASHTAG_POOL, k=random.randint(1, 3)):
                ht, _ = Hashtag.objects.get_or_create(name=hn.lower())
                foto.hashtags.add(ht)

        # FotoBoard : rattacher une partie des fotos aux boards du même auteur
        author_boards = boards_by_user.get(author.id, [])
        if author_boards and random.random() < 0.45:
            b = random.choice(author_boards)
            FotoBoard.objects.update_or_create(
                foto=pin,
                board=b,
                defaults={'position': random.randint(0, 40)},
            )

        created_fotos.append(foto)
        if is_story:
            story_fotos.append(foto)

        # Variantes pour quelques stories Pro / Plus (image dupliquée)
        if (
            is_story
            and pr.subscription_plan in {Profile.PLAN_PLUS, Profile.PLAN_PRO}
            and random.random() < 0.35
            and foto.image
        ):
            foto.image.open('rb')
            raw = foto.image.read()
            foto.image.close()
            pv = FotoVariant(foto=pin, kind=FotoVariant.KIND_STORY)
            suf = Path(pin.image.name).suffix.lower() if foto.image and foto.image.name else '.jpg'
            if suf not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                suf = '.jpg'
            pv.image.save(f'story_variant_{pin.slug}{suf}', ContentFile(raw), save=True)

        # Historique provenance minimal
        if random.random() < 0.08:
            h = hashlib.sha256(f'{pin.id}-{pin.slug}'.encode()).hexdigest()
            FotoProvenanceEvent.objects.create(
                foto=pin,
                actor=author,
                action=FotoProvenanceEvent.ACTION_CREATE,
                previous_hash='',
                current_hash=h,
                metadata={'seed': True},
            )

        # Tags privés (Plus / Pro)
        if (
            pr.subscription_plan in {Profile.PLAN_PLUS, Profile.PLAN_PRO}
            and random.random() < 0.12
        ):
            PrivatePinTag.objects.get_or_create(
                user=author,
                foto=pin,
                tag=random.choice(['brief', 'client-a', 'draft', 'à-revoir']),
            )

        if temp_img:
            temp_img.close()

        if (i - 99) % 80 == 0:
            logger.info(f'  … {i - 99}/{pin_target} pins')

    logger.info(f'Pins créés : {len(created_fotos)} dont {len(story_fotos)} stories.')

    david_u = User.objects.filter(username='david1anato').first()
    if david_u and topics_by_name:
        d_boards = boards_by_user.get(david_u.id, [])
        topic_keys = list(topics_by_name.keys())
        david_queries = ['portrait', 'studio', 'benin', 'lagos', 'texture', 'gradient', 'sunset', 'grid']
        logger.info('Pins additionnels pour david1anato…')
        for di in range(180):
            q = david_queries[di % len(david_queries)]
            topic = random.choice(topic_keys)
            topic_obj = topics_by_name[topic]
            sid = 70000 + di
            temp_img, media_fname = fetch_seed_image_file(f'david_{sid}_{q}', skip_network)
            vis = Foto.VISIBILITY_PUBLIC if random.random() < 0.88 else Foto.VISIBILITY_FOLLOWERS
            is_story = random.random() < 0.12
            foto = Foto.objects.create(
                title=f'David — {q.capitalize()} #{di + 1}',
                description=f'Seed tableau David Anato · {topic}.',
                author=david_u,
                topic=topic_obj,
                visibility=vis,
                link=f'https://fotoce.invalid/ref/david/{sid}' if random.random() < 0.12 else '',
                is_story=is_story,
                **random_foto_content_flags(),
            )
            if attach_image_to_pin(pin, temp_img, media_fname, skip_network):
                foto.refresh_from_db()
            if d_boards and random.random() < 0.78:
                b = random.choice(d_boards)
                FotoBoard.objects.update_or_create(
                    foto=pin,
                    board=b,
                    defaults={'position': random.randint(0, 60)},
                )
            created_fotos.append(foto)
            if is_story:
                story_fotos.append(foto)
            if temp_img:
                temp_img.close()
        logger.info(f'Pins David : +180 (boards remplis).')


    # Stories additionnelles pour garantir plusieurs stories par utilisateur « créatif »
    boost_users = [
        User.objects.filter(username=u).first()
        for u in ('clara', 'max', 'emma', 'leo', 'sofia')
    ]
    boost_users = [u for u in boost_users if u]
    extra_story_queries = ['sunset', 'studio', 'texture', 'gallery', 'urban', 'slowlife']
    for j, author in enumerate(boost_users * 4):
        topic_obj = topics_by_name[random.choice(topic_names)]
        q = extra_story_queries[j % len(extra_story_queries)]
        sid = 9000 + j
        temp_img, media_fname = fetch_seed_image_file(f'story_extra_{sid}_{q}', skip_network)
        foto = Foto.objects.create(
            title=f'Story — {author.username} · {q}',
            description=f'Story seed #{j} ({author.profile.subscription_plan}).',
            author=author,
            topic=topic_obj,
            visibility=Foto.VISIBILITY_PUBLIC,
            is_story=True,
            **random_foto_content_flags(),
        )
        attach_image_to_pin(pin, temp_img, media_fname, skip_network)
        story_fotos.append(foto)
        created_fotos.append(foto)
        if temp_img:
            temp_img.close()

    logger.info(f'Après boost stories : {len(story_fotos)} stories au total.')

    finalize_seed_stories_for_active_ring(story_fotos)

    seed_foto_feed_thumbnails(created_fotos)
    seed_foto_variants_square_sample(created_fotos)

    # Interactions aléatoires (likes/saves/views) pour les fotos publics
    public_fotos = [p for p in created_fotos if p.visibility == Foto.VISIBILITY_PUBLIC]
    sample_pins = random.sample(public_fotos, min(160, len(public_fotos)))

    logger.info('Likes, saves, vues, recherches…')
    for foto in sample_pins:
        likers = random.sample(regular_users, k=min(random.randint(1, 7), len(regular_users)))
        for liker in likers:
            if liker.id != foto.author_id:
                Like.objects.get_or_create(user=liker, foto=pin)

        savers = random.sample(regular_users, k=min(random.randint(0, 4), len(regular_users)))
        for saver in savers:
            if saver.id != foto.author_id:
                Save.objects.get_or_create(user=saver, foto=pin)

        viewers = random.sample(regular_users, k=min(random.randint(1, 5), len(regular_users)))
        for viewer in viewers:
            FotoViewEvent.objects.create(user=viewer, foto=pin)

    seed_david_fan_army(david_user)

    queries_search = ['tattoo', 'salon', 'minimal', 'cake', 'street', 'zen', 'loft']
    for u in random.sample(regular_users, min(6, len(regular_users))):
        for _ in range(random.randint(2, 6)):
            SearchInteraction.objects.create(
                user=u,
                query=random.choice(queries_search),
            )

    # Commentaires & réponses (couverture élargie + mentions @)
    logger.info('Commentaires…')
    if not public_fotos:
        comment_pins = []
    else:
        n_sample = min(len(public_fotos), max(160, len(public_fotos) // 3))
        comment_foto_ids = set(random.sample(public_fotos, n_sample))
        david_ref = User.objects.filter(username='david1anato').first()
        if david_ref:
            david_public = [
                p for p in public_fotos if p.author_id == david_ref.id
            ]
            if david_public:
                n_d = min(len(david_public), 70)
                comment_foto_ids.update(random.sample(david_public, n_d))
        comment_pins = list(comment_foto_ids)
        random.shuffle(comment_pins)

    all_users_for_comments = regular_users + [admin]

    for foto in comment_pins:
        authors_pool = [x for x in all_users_for_comments if x.id != foto.author_id]
        if not authors_pool:
            continue
        n_root = random.choices([1, 2, 3, 4, 5], weights=[18, 35, 28, 13, 6], k=1)[0]
        roots: list[Comment] = []
        for _ in range(n_root):
            cu = random.choice(authors_pool)
            base_txt = random.choice(COMMENT_SNIPPETS_FR)
            if random.random() < 0.15:
                base_txt += ' #design'
            if random.random() < 0.42:
                mention_opts = [x.username for x in authors_pool if x.id != cu.id]
                if mention_opts:
                    m = random.choice(mention_opts)
                    base_txt = f'{base_txt.rstrip()} @{m}'
            use_gif = (
                profiles_by_username[cu.username].subscription_plan != Profile.PLAN_FREE
                and random.random() < 0.22
            )
            gif_url_val = (
                'https://media.giphy.com/media/l0MYC0LajPoPotuRu/giphy.gif'
                if use_gif
                else ''
            )
            mentions_seed = extract_mentions(base_txt)
            c = Comment.objects.create(
                user=cu,
                foto=pin,
                text=base_txt,
                gif_url=gif_url_val,
                original_language='fr',
                mentions=mentions_seed,
            )
            if '#' in base_txt:
                ht_part = base_txt.split('#')[-1].strip().split()[0]
                if ht_part:
                    ht, _ = Hashtag.objects.get_or_create(name=ht_part.lower()[:99])
                    c.hashtags.add(ht)
            roots.append(c)

        # Réponses (souvent plusieurs)
        if roots and random.random() < 0.72:
            parent = random.choice([c for c in roots if c.parent_id is None] or roots)
            replier_pool = [x for x in authors_pool if x.id != parent.user_id]
            if replier_pool:
                replier = random.choice(replier_pool)
                rtxt = random.choice(COMMENT_REPLY_SNIPPETS_FR)
                if random.random() < 0.35:
                    moz = random.choice([x.username for x in authors_pool if x.id != replier.id])
                    rtxt = f'{rtxt} @{moz}'
                child = Comment.objects.create(
                    user=replier,
                    foto=pin,
                    text=rtxt,
                    parent=parent,
                    original_language='fr',
                    mentions=extract_mentions(rtxt),
                )
                roots.append(child)

                if random.random() < 0.45:
                    rp2 = random.choice([x for x in replier_pool if x.id != replier.id])
                    rtxt2 = random.choice(COMMENT_REPLY_SNIPPETS_FR)
                    gc = Comment.objects.create(
                        user=rp2,
                        foto=pin,
                        text=rtxt2,
                        parent=child,
                        original_language='fr',
                        mentions=extract_mentions(rtxt2),
                    )
                    roots.append(gc)

        # Likes sur commentaires
        for c in roots:
            likers_c = random.sample(authors_pool, k=min(random.randint(1, 4), len(authors_pool)))
            for lc in likers_c:
                CommentLike.objects.get_or_create(user=lc, comment=c)

    seed_contest_data(public_fotos, regular_users)

    seed_monetization(
        admin,
        public_fotos,
        topics_by_name,
        profiles_by_username,
        skip_network,
    )

    seed_content_sample_reports(public_fotos, regular_users)
    seed_user_blocks_sample()

    # Notifications factices (variété de types)
    logger.info('Notifications…')
    notif_specs = []
    if len(regular_users) >= 2:
        u1, u2 = regular_users[0], regular_users[1]
        pin0 = public_fotos[0] if public_fotos else None
        if pin0:
            notif_specs.append(
                Notification(
                    recipient=u2,
                    sender=u1,
                    notification_type='like',
                    message=f'{u1.username} a aimé votre foto.',
                    foto_id=pin0.id,
                    foto_slug=pin0.slug,
                )
            )
        notif_specs.append(
            Notification(
                recipient=regular_users[-1],
                sender=u1,
                notification_type='follow',
                message=f'{u1.username} vous suit.',
            )
        )
        notif_specs.append(
            Notification(
                recipient=u1,
                sender=None,
                notification_type='welcome',
                title='Bienvenue',
                message='Merci de tester Fotoce (seed).',
            )
        )
        clara_n = User.objects.filter(username='clara').first()
        nina_n = User.objects.filter(username='nina').first()
        if clara_n and nina_n:
            notif_specs.append(
                Notification(
                    recipient=nina_n,
                    sender=clara_n,
                    notification_type='board_invite',
                    title='Invitation tableau',
                    message='Clara vous invite à collaborer sur un tableau (seed).',
                    metadata={'seed': True},
                )
            )
    Notification.objects.bulk_create(notif_specs)

    # Abonnements push factices (endpoint unique pour les tests UI)
    logger.info('Push subscriptions (factices)…')

    for u in regular_users[: min(3, len(regular_users))]:
        PushSubscription.objects.create(
            user=u,
            endpoint=f'https://updates.seed.fotoce.invalid/push/{secrets.token_hex(16)}',
            p256dh=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii').rstrip('=')[
                :255
            ],
            auth=base64.urlsafe_b64encode(secrets.token_bytes(16)).decode('ascii').rstrip('=')[
                :255
            ],
            user_agent='SeedScript/1.0',
        )

    for u in regular_users[: min(2, len(regular_users))]:
        ExpoPushToken.objects.get_or_create(
            token=f'expo-seed-fotoce-{u.id}',
            defaults={
                'user': u,
                'platform': 'seed',
                'user_agent': 'FotoceSeed/Expo',
                'is_active': True,
            },
        )

    # Paiements & tickets support (références factices uniques)
    logger.info('Paiements & tickets…')
    pay_rows = []
    for idx, u in enumerate(regular_users[:5]):
        if u.profile.subscription_plan == Profile.PLAN_FREE:
            continue
        pay_rows.append(
            SubscriptionPayment(
                user=u,
                plan=u.profile.subscription_plan,
                billing_cycle=SubscriptionPayment.BILLING_MONTHLY,
                amount=4900 if u.profile.subscription_plan == Profile.PLAN_PRO else 2500,
                currency_iso='XOF',
                fedapay_transaction_id=f'seed_tx_{uuid.uuid4().hex[:20]}',
                status=(
                    SubscriptionPayment.STATUS_APPROVED
                    if idx % 2 == 0
                    else SubscriptionPayment.STATUS_PENDING
                ),
                fedapay_payload={'seed': True},
            )
        )
    du_pay = User.objects.filter(username='david1anato').first()
    if du_pay and du_pay.profile.subscription_plan == Profile.PLAN_PRO:
        pay_rows.append(
            SubscriptionPayment(
                user=du_pay,
                plan=Profile.PLAN_PRO,
                billing_cycle=SubscriptionPayment.BILLING_YEARLY,
                amount=47000,
                currency_iso='XOF',
                fedapay_transaction_id=f'seed_tx_{uuid.uuid4().hex[:20]}',
                status=SubscriptionPayment.STATUS_APPROVED,
                fedapay_payload={'seed': True, 'david': True},
            )
        )
    SubscriptionPayment.objects.bulk_create(pay_rows)

    SupportTicket.objects.create(
        user=random.choice(regular_users),
        subject='Question facturation seed',
        message='Est-ce que la facture mensuelle peut être envoyée par mail ?',
        status=SupportTicket.STATUS_OPEN,
        priority=SupportTicket.PRIORITY_NORMAL,
    )
    SupportTicket.objects.create(
        user=random.choice(regular_users),
        subject='Bug affichage board',
        message='Les fotos ne se réordonnent pas sur Safari.',
        status=SupportTicket.STATUS_IN_PROGRESS,
        priority=SupportTicket.PRIORITY_PRIORITY,
    )

    karim_u = User.objects.filter(username='karim').first()
    lucas_u = User.objects.filter(username='lucas').first()
    if david_user and karim_u and lucas_u:
        try:
            seed_subscription_seat_hub_demo(david_user, karim_u, lucas_u)
        except Exception as exc:
            logger.error(f'Subscription sièges (seed) ignoré : {exc}')

    exp_otp = dj_tz.now() + timedelta(minutes=10)
    EmailOTP.objects.update_or_create(
        user=admin,
        defaults={'otp_code': '424242', 'expires_at': exp_otp},
    )

    logger.info(
        'Seed terminé — connexion test : password123 — '
        f'réseau images seed={"off" if skip_network else "on"} — '
        f'{len(regular_users)} utilisateurs — '
        f'pins distants={SEED_IMAGE_STATS["pin_remote"]} '
        f'placeholders={SEED_IMAGE_STATS["pin_placeholder"]} '
        f'feed_thumbs={SEED_IMAGE_STATS["pin_feed_thumb"]} '
        f'avatars={SEED_IMAGE_STATS["avatar_remote"]}.'
    )


if __name__ == '__main__':
    seed_data()
