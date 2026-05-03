"""
Seed complet pour développement / démo Pinova.

Usage :
  python seed_data.py

Variables d'environnement optionnelles :
  SEED_SUPERUSER_USERNAME / SEED_SUPERUSER_EMAIL / SEED_SUPERUSER_PASSWORD
  SEED_PIN_COUNT          — nombre de pins « catalogue » (défaut 420)
  SEED_SKIP_NETWORK=1     — pas de téléchargement distant ; placeholders PNG uniquement en local.

  Images avec réseau : picsum (seed, id, aléatoire, grayscale),
  placehold.co (.png/.jpg/.webp + couleur), dummyimage (.png/.gif),
  placebear.com, placekitten, baconmockup, dicebear (png/webp),
  miniatures Wikimedia Commons (JPEG).

Les utilisateurs de test ont le mot de passe : password123

Modèles couverts (création ou nettoyage) : User ; Profile ; EmailOTP ; SubscriptionPricing ;
PinovaSubscriptionConfig ; SubscriptionPayment ; SubscriptionSeatInvitation ; SubscriptionSeatMember ;
SupportTicket ; UserBlock ; Notification ; PushSubscription ; Topic ; TopicTranslation ; LegalDocument ;
Hashtag ; Board ; BoardCollaborationInvite ; Pin ; PinVariant ; PinBoard ; Save ; Like ; Comment ;
CommentLike ; ContentReport ; PrivatePinTag ; PinProvenanceEvent ; PinViewEvent ; SearchInteraction.
"""
from __future__ import annotations

import hashlib
import os
import random
import secrets
import base64
import uuid
from datetime import timedelta, date
from pathlib import Path
import re
from urllib.parse import quote

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')
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
    PinovaSubscriptionConfig,
    Profile,
    SubscriptionPayment,
    SubscriptionPricing,
    SubscriptionSeatInvitation,
    SubscriptionSeatMember,
    SupportTicket,
    UserBlock,
)
from accounts.subscription_seats import generate_invite_plain_token_and_hash, grant_member_seat
from notifications.models import Notification, PushSubscription
from pins.serializers import extract_mentions
from pins.models import (
    Board,
    BoardCollaborationInvite,
    Comment,
    CommentLike,
    ContentReport,
    Hashtag,
    LegalDocument,
    Like,
    Pin,
    PinBoard,
    PinProvenanceEvent,
    PinVariant,
    PinViewEvent,
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
    'pinova',
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
        print(f"Superuser '{username}' créé.")
        return superuser

    if superuser.email != email:
        superuser.email = email
    if not superuser.is_staff:
        superuser.is_staff = True
    if not superuser.is_superuser:
        superuser.is_superuser = True

    superuser.set_password(password)
    superuser.save()
    print(f"Superuser '{username}' mis à jour.")
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
            headers={'User-Agent': 'PinovaSeed/1.1 (+https://pinova.invalid/seed)', 'Accept': 'image/*'},
        )
        if response.status_code != 200:
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
        img_temp.write(response.content)
        img_temp.flush()
        return img_temp, ext
    except Exception:
        pass
    return None, None


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
        s = 'pinova'
    return s[:max_len]


def candidate_seed_image_urls(seed_key: str, width: int, height: int) -> list[str]:
    """Plusieurs hôtes ; PNG / JPG / WebP explicites ou JPEG via redirections picsum."""
    safe = _safe_seed_slug(f'{seed_key}_{width}x{height}')
    short_txt = quote(_safe_seed_slug(seed_key, 10))
    hid = abs(hash(str(seed_key))) % 999 + 1
    wl, hh = sorted((width, height))
    wk, hk = wl, hh
    hex_bg = f'{(abs(hash(seed_key)) >> 16) & 0xFFFFFF:06x}'
    hex_fg = 'eeeeee'
    av_seed = _safe_seed_slug(seed_key, 48)
    smax = max(128, min(width, height, 512))
    wiki_thumb = random.choice(('240', '320', '440', '480'))
    return [
        f'https://picsum.photos/seed/{safe}/{width}/{height}',
        f'https://picsum.photos/id/{hid}/{width}/{height}',
        f'https://picsum.photos/id/{(hid % 200) + 1}/{width}/{height}?grayscale',
        f'https://picsum.photos/{width}/{height}?random={hid}',
        f'https://placehold.co/{width}x{height}.png',
        f'https://placehold.co/{width}x{height}.jpg',
        f'https://placehold.co/{width}x{height}.webp',
        f'https://placehold.co/{width}x{height}/{hex_bg}/{hex_fg}.png',
        f'https://dummyimage.com/{width}x{height}/{hex_bg}/{hex_fg}.png&text={short_txt}',
        f'https://dummyimage.com/{width}x{height}/e2e8f0/0f172a.gif&text=S',
        f'https://placebear.com/{width}/{height}',
        f'http://placekitten.com/{wk}/{hk}',
        f'http://placekitten.com/g/{wk}/{hk}',
        f'https://baconmockup.com/{width}/{height}',
        f'https://picsum.photos/seed/alt_{safe}/{height}/{width}',
        f'https://api.dicebear.com/9.x/avataaars/png?seed={av_seed}&size={smax}',
        f'https://api.dicebear.com/9.x/notionists/webp?seed={av_seed}&size={smax}',
        (
            'https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/'
            'Sunflower_from_Silesia_UK.jpg/{w}px-Sunflower_from_Silesia_UK.jpg'
        ).format(w=wiki_thumb),
        (
            'https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/'
            'Cat03.jpg/{w}px-Cat03.jpg'
        ).format(w=wiki_thumb),
    ]


def fetch_seed_image_file(seed_key: str, skip_network: bool, tries: int = 10):
    """Teste jusqu’à `tries` URLs parmi des fournisseurs et formats variés."""
    if skip_network:
        return None, 'seed_offline.png'
    w, h = random.choice(SEED_IMAGE_DIMENSIONS)
    urls = candidate_seed_image_urls(seed_key, w, h)
    random.shuffle(urls)
    for url in urls[: max(tries, 1)]:
        tmp, ext = download_image_to_temp(url)
        if tmp:
            return tmp, f'{_safe_seed_slug(seed_key, 52)}.{ext}'
    return None, 'seed_failed.jpg'


def placeholder_png_bytes(seed: str = 'pinova') -> bytes:
    """Petite image PNG valide (1×1 pixel) pour mode hors réseau."""
    # PNG minimal rougeâtre via données fixes ultra compactes — évite Pillow en dépendance du seed.
    return bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
        '0000000a49444154789c6300010000050001790000000049454e44ae426082'
    )


def cleanup_existing_pin_media():
    print('Suppression des médias pins / variants / commentaires…')
    for v in PinVariant.objects.iterator():
        if v.image:
            v.image.delete(save=False)
    PinVariant.objects.all().delete()

    for c in Comment.objects.exclude(media='').iterator():
        if c.media:
            c.media.delete(save=False)

    for pin in Pin.objects.exclude(image='').iterator():
        if pin.image:
            pin.image.delete(save=False)

    pins_dir = Path(settings.MEDIA_ROOT) / 'pins'
    if pins_dir.exists():
        for file_path in pins_dir.rglob('*'):
            if file_path.is_file():
                file_path.unlink(missing_ok=True)

    Pin.objects.all().delete()
    Hashtag.objects.all().delete()


def cleanup_relational_data():
    """Notifications, interactions, boards (orphelins), etc."""
    print('Nettoyage des données relationnelles…')
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
    PinViewEvent.objects.all().delete()
    SearchInteraction.objects.all().delete()
    PinProvenanceEvent.objects.all().delete()
    PrivatePinTag.objects.all().delete()
    PinBoard.objects.all().delete()

    Board.collaborators.through.objects.all().delete()
    Board.objects.all().delete()

    TopicTranslation.objects.all().delete()


def cleanup_seed():
    cleanup_relational_data()
    cleanup_existing_pin_media()


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
    print('Tarifs SubscriptionPricing à jour.')


def seed_pinova_subscription_config():
    cfg = PinovaSubscriptionConfig.load()
    if cfg.annual_discount_percent != 12:
        cfg.annual_discount_percent = 12
        cfg.save(update_fields=['annual_discount_percent'])
    print('PinovaSubscriptionConfig (singleton) à jour.')


def seed_legal_documents():
    """Pages légales + contact (alignées sur pins.legal_defaults)."""
    from pins.legal_defaults import (
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
            'contact_email': 'support@pinova.app',
            'translations_cache': {},
        },
    )
    print('LegalDocument (privacy / terms / contact) à jour.')


def random_pin_content_flags() -> dict:
    """Politique commentaires + flags modération / sensible (échantillon)."""
    return {
        'comments_policy': random.choices(
            [Pin.COMMENTS_OPEN, Pin.COMMENTS_FOLLOWERS_ONLY, Pin.COMMENTS_CLOSED],
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
    print('BoardCollaborationInvite (pending) créée.')


def seed_pin_variants_square_sample(created_pins: list[Pin]) -> None:
    """Variantes carrées (hors story) pour tester les crops API / front."""
    candidates = [p for p in created_pins if p.image and not p.is_story]
    random.shuffle(candidates)
    n = 0
    for pin in candidates[:14]:
        if PinVariant.objects.filter(pin=pin, kind=PinVariant.KIND_SQUARE).exists():
            continue
        try:
            pin.image.open('rb')
            raw = pin.image.read()
            pin.image.close()
        except Exception:
            continue
        suf = Path(pin.image.name).suffix.lower() if pin.image.name else '.jpg'
        if suf not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
            suf = '.jpg'
        pv = PinVariant(pin=pin, kind=PinVariant.KIND_SQUARE)
        pv.image.save(f'variant_sq_{pin.slug}{suf}', ContentFile(raw), save=True)
        n += 1
    print(f'PinVariant carré (seed) : {n} fichiers.')


def seed_content_sample_reports(public_pins: list[Pin], regular_users: list[User]) -> None:
    """Signalements pin / profil / commentaire (contraintes uniques)."""
    if len(public_pins) < 2 or len(regular_users) < 4:
        print('ContentReport : ignoré (données insuffisantes).')
        return
    pin_a, pin_b = public_pins[0], public_pins[1]
    r0, r1, r2 = regular_users[0], regular_users[1], regular_users[2]
    target = next((u for u in regular_users if u.id not in (r0.id, r1.id, r2.id)), regular_users[3])

    ContentReport.objects.get_or_create(
        reporter=r0,
        pin=pin_a,
        defaults={'category': 'spam', 'details': 'Seed : signalement pin.', 'reason': ''},
    )
    ContentReport.objects.get_or_create(
        reporter=r1,
        reported_user=target,
        defaults={'category': 'harassment', 'details': 'Seed : signalement profil.', 'reason': ''},
    )
    c = Comment.objects.filter(pin=pin_b, parent__isnull=True).exclude(user=target).first()
    if c:
        ContentReport.objects.get_or_create(
            reporter=r2,
            comment=c,
            defaults={'category': 'other', 'details': 'Seed : signalement commentaire.', 'reason': ''},
        )
    print('ContentReport (échantillon) créés.')


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


def refresh_seed_story_created_dates(story_pins: list[Pin]) -> None:
    """Met à jour created_at des stories seed (bandeau « récent », libellés relatifs crédibles)."""
    if not story_pins:
        return
    now = dj_tz.now()
    for p in story_pins:
        minutes_ago = random.randint(5, 36 * 60)
        Pin.objects.filter(pk=p.pk).update(created_at=now - timedelta(minutes=minutes_ago))
    print(f'Stories : {len(story_pins)} dates created_at mises à jour (aléatoire, ~5 min à 36 h).')


def attach_image_to_pin(pin: Pin, temp_img, fname: str, skip_network: bool) -> bool:
    stem = Path(fname).stem if fname else f'pin_{pin.pk}'
    if temp_img:
        pin.image.save(fname, File(temp_img))
        return True
    if skip_network:
        pin.image.save(
            f'{stem}.png',
            ContentFile(placeholder_png_bytes(str(pin.pk))),
            save=True,
        )
        return True
    pin.image.save(
        f'{stem}_fallback.png',
        ContentFile(placeholder_png_bytes(str(pin.slug))),
        save=True,
    )
    return True


def seed_data():
    print('Mise à jour complète de la base de données (seed)…')
    skip_network = os.environ.get('SEED_SKIP_NETWORK', '').lower() in ('1', 'true', 'yes')
    pin_target = int(os.environ.get('SEED_PIN_COUNT', '420'))

    cleanup_seed()

    admin = ensure_superuser()
    User.objects.exclude(is_superuser=True).delete()

    seed_subscription_pricing()
    seed_pinova_subscription_config()
    seed_legal_documents()

    users: list[User] = [admin]
    profiles_by_username: dict[str, Profile] = {}

    print('Création des utilisateurs et profils…')
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
            if profile.tips_enabled:
                profile.tips_url = f'https://ko-fi.com/{uname}'
            profile.subscription_renewal_at = dj_tz.now() + timedelta(days=20)
        elif plan == Profile.PLAN_PLUS:
            profile.translation_quota_monthly = 200
            profile.subscription_renewal_at = dj_tz.now() + timedelta(days=12)
        else:
            profile.translation_quota_monthly = 5

        # Un profil privé pour tester les règles de visibilité
        if uname == 'nina':
            profile.private_profile = True
        profile.save()
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
    dprof.bio = 'Créateur Pinova — design, photo & voyage.'
    dprof.avatar_color = '#e11d48'
    dprof.subscription_seat_bundle = 'family'
    dprof.discoverable_profile = True
    dprof.preferred_language = 'fr'
    dprof.translation_quota_monthly = 5000
    dprof.subscription_renewal_at = dj_tz.now() + timedelta(days=25)
    dprof.private_profile = False
    dprof.birth_date = date(1995, 6, 15)
    dprof.tips_enabled = True
    dprof.tips_url = 'https://ko-fi.com/david1anato'
    dprof.save()
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

    print('Création des boards…')
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

    created_pins: list[Pin] = []
    story_pins: list[Pin] = []

    print(f'Création de ~{pin_target} pins — multi-sources JPG/PNG/WebP/GIF, dimensions variées (stories free/plus/pro)…')

    def maybe_visibility(u: User, topic_obj: Topic) -> str:
        pr = profiles_by_username[u.username]
        if pr.private_profile and random.random() < 0.25:
            return Pin.VISIBILITY_FOLLOWERS
        roll = random.random()
        if roll < 0.82:
            return Pin.VISIBILITY_PUBLIC
        if roll < 0.94:
            return Pin.VISIBILITY_FOLLOWERS
        return Pin.VISIBILITY_PRIVATE

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

        scheduled = None
        if pr.subscription_plan == Profile.PLAN_PRO and random.random() < 0.04:
            scheduled = dj_tz.now() + timedelta(days=random.randint(1, 14))

        pin = Pin.objects.create(
            title=f"Inspiration {query.capitalize()} {i + 1}",
            description=f"Découverte sur le thème {query} — {topic}. #seed",
            author=author,
            topic=topic_obj,
            visibility=vis,
            link=f'https://example.com/ref/{i}' if random.random() < 0.15 else '',
            is_story=is_story,
            scheduled_publish_at=scheduled,
            **random_pin_content_flags(),
        )

        if attach_image_to_pin(pin, temp_img, media_fname, skip_network):
            pin.refresh_from_db()

        if is_story:
            pin.refresh_story_expiry()
            pin.save(update_fields=['story_expires_at'])

        # Hashtags (sous-ensemble)
        if random.random() < 0.35:
            for hn in random.sample(HASHTAG_POOL, k=random.randint(1, 3)):
                ht, _ = Hashtag.objects.get_or_create(name=hn.lower())
                pin.hashtags.add(ht)

        # PinBoard : rattacher une partie des pins aux boards du même auteur
        author_boards = boards_by_user.get(author.id, [])
        if author_boards and random.random() < 0.45:
            b = random.choice(author_boards)
            PinBoard.objects.update_or_create(
                pin=pin,
                board=b,
                defaults={'position': random.randint(0, 40)},
            )

        created_pins.append(pin)
        if is_story:
            story_pins.append(pin)

        # Variantes pour quelques stories Pro / Plus (image dupliquée)
        if (
            is_story
            and pr.subscription_plan in {Profile.PLAN_PLUS, Profile.PLAN_PRO}
            and random.random() < 0.35
            and pin.image
        ):
            pin.image.open('rb')
            raw = pin.image.read()
            pin.image.close()
            pv = PinVariant(pin=pin, kind=PinVariant.KIND_STORY)
            suf = Path(pin.image.name).suffix.lower() if pin.image and pin.image.name else '.jpg'
            if suf not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                suf = '.jpg'
            pv.image.save(f'story_variant_{pin.slug}{suf}', ContentFile(raw), save=True)

        # Historique provenance minimal
        if random.random() < 0.08:
            h = hashlib.sha256(f'{pin.id}-{pin.slug}'.encode()).hexdigest()
            PinProvenanceEvent.objects.create(
                pin=pin,
                actor=author,
                action=PinProvenanceEvent.ACTION_CREATE,
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
                pin=pin,
                tag=random.choice(['brief', 'client-a', 'draft', 'à-revoir']),
            )

        if temp_img:
            temp_img.close()

        if (i - 99) % 80 == 0:
            print(f'  … {i - 99}/{pin_target} pins')

    print(f'Pins créés : {len(created_pins)} dont {len(story_pins)} stories.')

    david_u = User.objects.filter(username='david1anato').first()
    if david_u and topics_by_name:
        d_boards = boards_by_user.get(david_u.id, [])
        topic_keys = list(topics_by_name.keys())
        david_queries = ['portrait', 'studio', 'benin', 'lagos', 'texture', 'gradient', 'sunset', 'grid']
        print('Pins additionnels pour david1anato…')
        for di in range(180):
            q = david_queries[di % len(david_queries)]
            topic = random.choice(topic_keys)
            topic_obj = topics_by_name[topic]
            sid = 70000 + di
            temp_img, media_fname = fetch_seed_image_file(f'david_{sid}_{q}', skip_network)
            vis = Pin.VISIBILITY_PUBLIC if random.random() < 0.88 else Pin.VISIBILITY_FOLLOWERS
            is_story = random.random() < 0.12
            pin = Pin.objects.create(
                title=f'David — {q.capitalize()} #{di + 1}',
                description=f'Seed tableau David Anato · {topic}.',
                author=david_u,
                topic=topic_obj,
                visibility=vis,
                link=f'https://pinova.invalid/ref/david/{sid}' if random.random() < 0.12 else '',
                is_story=is_story,
                **random_pin_content_flags(),
            )
            if attach_image_to_pin(pin, temp_img, media_fname, skip_network):
                pin.refresh_from_db()
            if is_story:
                pin.refresh_story_expiry()
                pin.save(update_fields=['story_expires_at'])
            if d_boards and random.random() < 0.78:
                b = random.choice(d_boards)
                PinBoard.objects.update_or_create(
                    pin=pin,
                    board=b,
                    defaults={'position': random.randint(0, 60)},
                )
            created_pins.append(pin)
            if is_story:
                story_pins.append(pin)
            if temp_img:
                temp_img.close()
        print(f'Pins David : +180 (boards remplis).')


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
        pin = Pin.objects.create(
            title=f'Story — {author.username} · {q}',
            description=f'Story seed #{j} ({author.profile.subscription_plan}).',
            author=author,
            topic=topic_obj,
            visibility=Pin.VISIBILITY_PUBLIC,
            is_story=True,
            **random_pin_content_flags(),
        )
        attach_image_to_pin(pin, temp_img, media_fname, skip_network)
        pin.refresh_story_expiry()
        pin.save(update_fields=['story_expires_at'])
        story_pins.append(pin)
        created_pins.append(pin)
        if temp_img:
            temp_img.close()

    print(f'Après boost stories : {len(story_pins)} stories au total.')

    refresh_seed_story_created_dates(story_pins)

    seed_pin_variants_square_sample(created_pins)

    # Likes & saves croisés
    print('Likes, saves, vues, recherches…')
    public_pins = [p for p in created_pins if p.visibility == Pin.VISIBILITY_PUBLIC]
    sample_pins = random.sample(public_pins, min(160, len(public_pins)))

    for pin in sample_pins:
        likers = random.sample(regular_users, k=min(random.randint(1, 7), len(regular_users)))
        for liker in likers:
            if liker.id != pin.author_id:
                Like.objects.get_or_create(user=liker, pin=pin)

        savers = random.sample(regular_users, k=min(random.randint(0, 4), len(regular_users)))
        for saver in savers:
            if saver.id != pin.author_id:
                Save.objects.get_or_create(user=saver, pin=pin)

        viewers = random.sample(regular_users, k=min(random.randint(1, 5), len(regular_users)))
        for viewer in viewers:
            PinViewEvent.objects.create(user=viewer, pin=pin)

    queries_search = ['tattoo', 'salon', 'minimal', 'cake', 'street', 'zen', 'loft']
    for u in random.sample(regular_users, min(6, len(regular_users))):
        for _ in range(random.randint(2, 6)):
            SearchInteraction.objects.create(
                user=u,
                query=random.choice(queries_search),
            )

    # Commentaires & réponses (couverture élargie + mentions @)
    print('Commentaires…')
    if not public_pins:
        comment_pins = []
    else:
        n_sample = min(len(public_pins), max(160, len(public_pins) // 3))
        comment_pin_ids = set(random.sample(public_pins, n_sample))
        david_ref = User.objects.filter(username='david1anato').first()
        if david_ref:
            david_public = [
                p for p in public_pins if p.author_id == david_ref.id
            ]
            if david_public:
                n_d = min(len(david_public), 70)
                comment_pin_ids.update(random.sample(david_public, n_d))
        comment_pins = list(comment_pin_ids)
        random.shuffle(comment_pins)

    all_users_for_comments = regular_users + [admin]

    for pin in comment_pins:
        authors_pool = [x for x in all_users_for_comments if x.id != pin.author_id]
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
                pin=pin,
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
                    pin=pin,
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
                        pin=pin,
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

    seed_content_sample_reports(public_pins, regular_users)
    seed_user_blocks_sample()

    # Notifications factices (variété de types)
    print('Notifications…')
    notif_specs = []
    if len(regular_users) >= 2:
        u1, u2 = regular_users[0], regular_users[1]
        pin0 = public_pins[0] if public_pins else None
        if pin0:
            notif_specs.append(
                Notification(
                    recipient=u2,
                    sender=u1,
                    notification_type='like',
                    message=f'{u1.username} a aimé votre pin.',
                    pin_id=pin0.id,
                    pin_slug=pin0.slug,
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
                message='Merci de tester Pinova (seed).',
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
    print('Push subscriptions (factices)…')

    for u in regular_users[: min(3, len(regular_users))]:
        PushSubscription.objects.create(
            user=u,
            endpoint=f'https://updates.seed.pinova.invalid/push/{secrets.token_hex(16)}',
            p256dh=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii').rstrip('=')[
                :255
            ],
            auth=base64.urlsafe_b64encode(secrets.token_bytes(16)).decode('ascii').rstrip('=')[
                :255
            ],
            user_agent='SeedScript/1.0',
        )

    # Paiements & tickets support (références factices uniques)
    print('Paiements & tickets…')
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
        message='Les pins ne se réordonnent pas sur Safari.',
        status=SupportTicket.STATUS_IN_PROGRESS,
        priority=SupportTicket.PRIORITY_PRIORITY,
    )

    karim_u = User.objects.filter(username='karim').first()
    lucas_u = User.objects.filter(username='lucas').first()
    if david_user and karim_u and lucas_u:
        try:
            seed_subscription_seat_hub_demo(david_user, karim_u, lucas_u)
        except Exception as exc:
            print(f'Subscription sièges (seed) ignoré : {exc}')

    exp_otp = dj_tz.now() + timedelta(minutes=10)
    EmailOTP.objects.update_or_create(
        user=admin,
        defaults={'otp_code': '424242', 'expires_at': exp_otp},
    )

    print(
        'Seed terminé — connexion test : password123 — '
        f'réseau images seed={"off" if skip_network else "on"} — '
        f'{len(regular_users)} utilisateurs.'
    )


if __name__ == '__main__':
    seed_data()
