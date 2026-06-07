"""Tests accès médias /media/ — IDOR, URLs signées HMAC."""

import io
import time

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from pinova_backend.media_serving.access import build_media_signature
from pins.models import Pin


def _make_image(name: str = 'test.jpg') -> SimpleUploadedFile:
    try:
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (8, 8), color='red').save(buf, format='JPEG')
        content = buf.getvalue()
    except ImportError:
        content = b'\xff\xd8\xff\xd9'
    return SimpleUploadedFile(name, content, content_type='image/jpeg')


@override_settings(MEDIA_SIGNING_SECRET='test-media-signing-secret')
class MediaAccessTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user('author', 'author@example.com', 'Pinova2026!')
        self.other = User.objects.create_user('other', 'other@example.com', 'Pinova2026!')

    def _create_pin(self, *, visibility: str, is_story: bool = False) -> Pin:
        return Pin.objects.create(
            title='Test pin',
            author=self.author,
            visibility=visibility,
            is_story=is_story,
            image=_make_image(f'{visibility}-{"story" if is_story else "pin"}.jpg'),
        )

    def _signed_url(self, relative_path: str, user_id: int) -> str:
        exp = int(time.time()) + 3600
        sig = build_media_signature(relative_path, exp, user_id)
        return f'/media/{relative_path}?exp={exp}&sig={sig}&uid={user_id}'

    def test_private_pin_media_without_token_forbidden(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PRIVATE)
        response = self.client.get(f'/media/{pin.image.name}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_private_pin_media_with_valid_signed_url_ok(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PRIVATE)
        response = self.client.get(self._signed_url(pin.image.name, self.author.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_pin_signed_url_wrong_viewer_forbidden(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PRIVATE)
        response = self.client.get(self._signed_url(pin.image.name, self.other.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_pin_media_without_token_ok(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PUBLIC)
        response = self.client.get(f'/media/{pin.image.name}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_story_media_requires_signed_url(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PUBLIC, is_story=True)
        response = self.client.get(f'/media/{pin.image.name}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(self._signed_url(pin.image.name, self.author.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_expired_signed_url_forbidden(self):
        pin = self._create_pin(visibility=Pin.VISIBILITY_PRIVATE)
        exp = int(time.time()) - 120
        sig = build_media_signature(pin.image.name, exp, self.author.id)
        url = f'/media/{pin.image.name}?exp={exp}&sig={sig}&uid={self.author.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_path_traversal_forbidden(self):
        response = self.client.get('/media/../manage.py')
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
