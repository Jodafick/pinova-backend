"""Seed minimal pour load test home_feed (utilisateur + abonnements + fotos publics)."""
from __future__ import annotations

import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fotoce_backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User  # noqa: E402

from accounts.models import Profile  # noqa: E402
from fotos.models import Foto  # noqa: E402

LOADTEST_USER = os.environ.get('LOADTEST_USER', 'loadtest')
LOADTEST_EMAIL = os.environ.get('LOADTEST_EMAIL', 'loadtest@fotoce.local')
LOADTEST_PASSWORD = os.environ.get('LOADTEST_PASSWORD', 'password123')
AUTHOR_COUNT = int(os.environ.get('LOADTEST_AUTHOR_COUNT', '40'))
PINS_PER_AUTHOR = int(os.environ.get('LOADTEST_PINS_PER_AUTHOR', '15'))


def main() -> None:
    viewer, created = User.objects.get_or_create(
        username=LOADTEST_USER,
        defaults={'email': LOADTEST_EMAIL},
    )
    if created:
        viewer.set_password(LOADTEST_PASSWORD)
        viewer.save()
    viewer.profile.subscription_plan = Profile.PLAN_PRO
    viewer.profile.partner_ads_enabled = False
    viewer.profile.private_profile = False
    viewer.profile.save(
        update_fields=['subscription_plan', 'partner_ads_enabled', 'private_profile'],
    )

    following_ids: list[int] = []
    for i in range(AUTHOR_COUNT):
        author, _ = User.objects.get_or_create(
            username=f'loadauthor{i}',
            defaults={'email': f'loadauthor{i}@fotoce.local'},
        )
        if not author.has_usable_password():
            author.set_password(LOADTEST_PASSWORD)
            author.save(update_fields=['password'])
        author.profile.private_profile = False
        author.profile.save(update_fields=['private_profile'])
        viewer.profile.following.add(author.profile)
        following_ids.append(author.id)
        for j in range(PINS_PER_AUTHOR):
            slug = f'load-{i}-{j}'
            Foto.objects.get_or_create(
                author=author,
                slug=slug,
                defaults={
                    'title': f'Load foto {i}-{j}',
                    'visibility': Foto.VISIBILITY_PUBLIC,
                },
            )

    # Pins discover (auteurs non suivis)
    stranger, _ = User.objects.get_or_create(
        username='loadstranger',
        defaults={'email': 'loadstranger@fotoce.local'},
    )
    stranger.profile.private_profile = False
    stranger.profile.save(update_fields=['private_profile'])
    for j in range(PINS_PER_AUTHOR):
        slug = f'discover-{j}'
        Foto.objects.get_or_create(
            author=stranger,
            slug=slug,
            defaults={
                'title': f'Discover load {j}',
                'visibility': Foto.VISIBILITY_PUBLIC,
            },
        )

    print(
        f'OK loadtest seed — viewer={LOADTEST_USER} '
        f'following={len(following_ids)} authors × {PINS_PER_AUTHOR} fotos + discover',
    )


if __name__ == '__main__':
    main()
