"""
Seed complet pour développement / démo Pinova.

Usage :
  python seed_data.py

Variables d'environnement optionnelles :
  SEED_SUPERUSER_USERNAME / SEED_SUPERUSER_EMAIL / SEED_SUPERUSER_PASSWORD
  SEED_PIN_COUNT          — nombre de pins « catalogue » (défaut 420)
  SEED_SKIP_NETWORK=1     — pas de téléchargement picsum ; pins sans image (tests offline)

Les utilisateurs de test ont le mot de passe : password123
"""
from __future__ import annotations

import hashlib
import os
import random
import secrets
import base64
import uuid
from datetime import timedelta
from pathlib import Path

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')
django.setup()

import django.utils.timezone as dj_tz
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.temp import NamedTemporaryFile

from accounts.models import (
    EmailOTP,
    Profile,
    SubscriptionPayment,
    SubscriptionPricing,
    SupportTicket,
)
from notifications.models import Notification, PushSubscription
from pins.models import (
    Board,
    Comment,
    CommentLike,
    Hashtag,
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
    if requests is None:
        return None
    try:
        response = requests.get(url, timeout=25)
        if response.status_code == 200:
            img_temp = NamedTemporaryFile()
            img_temp.write(response.content)
            img_temp.flush()
            return img_temp
    except OSError:
        pass
    return None


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
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_MONTHLY, 2500, 30),
        (Profile.PLAN_PLUS, SubscriptionPricing.BILLING_YEARLY, 24000, 365),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_MONTHLY, 4900, 30),
        (Profile.PLAN_PRO, SubscriptionPricing.BILLING_YEARLY, 47000, 365),
    ]
    for plan, cycle, amount, days in catalog:
        SubscriptionPricing.objects.update_or_create(
            plan=plan,
            billing_cycle=cycle,
            defaults={
                'amount': amount,
                'duration_days': days,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )
    print('Tarifs SubscriptionPricing à jour.')


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


def attach_image_to_pin(pin: Pin, temp_img, fname: str, skip_network: bool) -> bool:
    if temp_img:
        pin.image.save(fname, File(temp_img))
        return True
    if skip_network:
        pin.image.save(
            fname.replace('.jpg', '.png'),
            ContentFile(placeholder_png_bytes(str(pin.pk))),
            save=True,
        )
        return True
    # Picsum indisponible : éviter un pin sans fichier
    pin.image.save(
        fname.replace('.jpg', '_fallback.png'),
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
        profile.avatar_color = random.choice([
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
        ])
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

    # Graphe de follows (pas symétrique)
    regular_users = [u for u in users if not u.is_superuser]
    for u in regular_users:
        others = [x for x in regular_users if x.id != u.id]
        for f in random.sample(others, k=min(4, len(others))):
            u.profile.following.add(f.profile)

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
        for bname, is_priv in board_names[: random.randint(2, 4)]:
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

    print(f'Création de ~{pin_target} pins (stories réparties free/plus/pro)…')

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
        img_url = f'https://picsum.photos/seed/{i}_{query}/600/900'
        temp_img = None if skip_network else download_image(img_url)

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
        )

        fname = f'{query}_{i}.jpg'
        if attach_image_to_pin(pin, temp_img, fname, skip_network):
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
            pv.image.save(f'story_variant_{pin.slug}.jpg', ContentFile(raw), save=True)

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
        img_url = f'https://picsum.photos/seed/story_extra_{sid}/600/900'
        temp_img = None if skip_network else download_image(img_url)
        pin = Pin.objects.create(
            title=f'Story — {author.username} · {q}',
            description=f'Story seed #{j} ({author.profile.subscription_plan}).',
            author=author,
            topic=topic_obj,
            visibility=Pin.VISIBILITY_PUBLIC,
            is_story=True,
        )
        attach_image_to_pin(pin, temp_img, f'story_boost_{sid}.jpg', skip_network)
        pin.refresh_story_expiry()
        pin.save(update_fields=['story_expires_at'])
        story_pins.append(pin)
        created_pins.append(pin)
        if temp_img:
            temp_img.close()

    print(f'Après boost stories : {len(story_pins)} stories au total.')

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

    # Commentaires & réponses
    print('Commentaires…')
    comment_pins = random.sample(
        public_pins,
        min(55, len(public_pins)),
    )
    all_users_for_comments = regular_users + [admin]

    for pin in comment_pins:
        authors_pool = [x for x in all_users_for_comments if x.id != pin.author_id]
        if not authors_pool:
            continue
        n_root = random.randint(1, 3)
        roots: list[Comment] = []
        for _ in range(n_root):
            cu = random.choice(authors_pool)
            base_txt = random.choice(COMMENT_SNIPPETS_FR)
            if random.random() < 0.15:
                base_txt += ' #design'
            use_gif = (
                profiles_by_username[cu.username].subscription_plan != Profile.PLAN_FREE
                and random.random() < 0.25
            )
            gif_url_val = (
                'https://media.giphy.com/media/l0MYC0LajPoPotuRu/giphy.gif'
                if use_gif
                else ''
            )
            c = Comment.objects.create(
                user=cu,
                pin=pin,
                text=base_txt,
                gif_url=gif_url_val,
                original_language='fr',
            )
            if '#' in base_txt:
                ht_part = base_txt.split('#')[-1].strip().split()[0]
                if ht_part:
                    ht, _ = Hashtag.objects.get_or_create(name=ht_part.lower()[:99])
                    c.hashtags.add(ht)
            roots.append(c)

        # Réponses
        if roots and random.random() < 0.55:
            parent = random.choice(roots)
            replier = random.choice([x for x in authors_pool if x.id != parent.user_id])
            child = Comment.objects.create(
                user=replier,
                pin=pin,
                text='Totalement d’accord 👍',
                parent=parent,
                original_language='fr',
            )
            roots.append(child)

        # Likes sur commentaires
        for c in roots:
            likers_c = random.sample(authors_pool, k=min(3, len(authors_pool)))
            for lc in likers_c:
                CommentLike.objects.get_or_create(user=lc, comment=c)

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

    print(
        'Seed terminé — connexion test : password123 — '
        f'réseau picsum={"off" if skip_network else "on"} — '
        f'{len(regular_users)} utilisateurs.'
    )


if __name__ == '__main__':
    seed_data()
