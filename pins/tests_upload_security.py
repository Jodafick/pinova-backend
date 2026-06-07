"""Tests validation uploads sécurisés (magic bytes, polyglot, taille, re-encodage)."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import serializers
from rest_framework.test import APITestCase

from pins.upload_security import (
    CODE_IMAGE_INVALID,
    CODE_IMAGE_POLYGLOT,
    CODE_IMAGE_TOO_LARGE,
    CODE_VIDEO_INVALID,
    secure_image_upload,
    secure_video_upload,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def _jpeg_bytes() -> bytes:
    if Image is None:
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xd9'
        )
    buf = io.BytesIO()
    Image.new('RGB', (32, 32), 'blue').save(buf, format='JPEG')
    return buf.getvalue()


def _png_labeled_as_jpg() -> SimpleUploadedFile:
    if Image is None:
        png_head = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
            b'\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        return SimpleUploadedFile('fake.jpg', png_head, content_type='image/jpeg')
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), 'green').save(buf, format='PNG')
    return SimpleUploadedFile('fake.jpg', buf.getvalue(), content_type='image/jpeg')


def _tiny_mp4() -> SimpleUploadedFile:
    # Minimal ISO BMFF header (ftyp mp42) — suffisant pour filetype video/mp4.
    payload = (
        b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'
        b'\x00\x00\x00\x08free'
    )
    return SimpleUploadedFile('clip.mp4', payload, content_type='video/mp4')


@override_settings(PIN_IMAGE_MAX_SIZE_MB=10, PIN_IMAGE_JPEG_QUALITY=85)
class UploadSecurityTests(APITestCase):
    def test_valid_jpeg_is_reencoded(self):
        uploaded = SimpleUploadedFile('photo.jpg', _jpeg_bytes(), content_type='image/jpeg')
        out = secure_image_upload(uploaded, kind='pin')
        self.assertTrue(out.name.endswith('.jpg'))
        self.assertEqual(out.content_type, 'image/jpeg')
        self.assertLess(out.size, len(_jpeg_bytes()) + 1024)

    def test_polyglot_png_as_jpg_rejected(self):
        uploaded = _png_labeled_as_jpg()
        with self.assertRaises(serializers.ValidationError) as ctx:
            secure_image_upload(uploaded, kind='pin')
        self.assertEqual(str(ctx.exception.detail[0]), CODE_IMAGE_POLYGLOT)

    def test_oversized_image_rejected(self):
        uploaded = SimpleUploadedFile(
            'big.jpg',
            _jpeg_bytes() + (b'0' * (11 * 1024 * 1024)),
            content_type='image/jpeg',
        )
        with self.assertRaises(serializers.ValidationError) as ctx:
            secure_image_upload(uploaded, kind='pin')
        self.assertEqual(str(ctx.exception.detail[0]), CODE_IMAGE_TOO_LARGE)

    def test_invalid_image_magic_rejected(self):
        uploaded = SimpleUploadedFile('x.jpg', b'not-an-image-at-all', content_type='image/jpeg')
        with self.assertRaises(serializers.ValidationError) as ctx:
            secure_image_upload(uploaded, kind='pin')
        self.assertEqual(str(ctx.exception.detail[0]), CODE_IMAGE_INVALID)

    def test_valid_mp4_passes_magic_validation(self):
        uploaded = _tiny_mp4()
        out = secure_video_upload(uploaded)
        self.assertEqual(out.name, 'clip.mp4')

    def test_invalid_video_rejected(self):
        uploaded = SimpleUploadedFile('clip.mp4', b'hello-video', content_type='video/mp4')
        with self.assertRaises(serializers.ValidationError) as ctx:
            secure_video_upload(uploaded)
        self.assertEqual(str(ctx.exception.detail[0]), CODE_VIDEO_INVALID)
