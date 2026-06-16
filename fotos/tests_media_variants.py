"""Tests génération thumbnail feed."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from fotos.media_variants import FEED_THUMB_MAX_SIDE, ensure_foto_feed_thumbnail
from fotos.models import Foto, FotoVariant, Topic

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def _large_jpeg_upload() -> SimpleUploadedFile:
    if Image is None:
        return SimpleUploadedFile('big.jpg', b'\xff\xd8\xff\xd9', content_type='image/jpeg')
    buf = io.BytesIO()
    Image.new('RGB', (1200, 1600), 'red').save(buf, format='JPEG')
    return SimpleUploadedFile('big.jpg', buf.getvalue(), content_type='image/jpeg')


class FeedThumbnailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username='thumbuser', password='x')
        cls.topic = Topic.objects.create(name='Art')

    def test_creates_feed_variant_max_400px(self):
        if Image is None:
            self.skipTest('Pillow not installed')
        foto = Foto.objects.create(
            title='Thumb test',
            author=self.user,
            topic=self.topic,
            image=_large_jpeg_upload(),
        )
        variant = ensure_foto_feed_thumbnail(foto)
        self.assertIsNotNone(variant)
        self.assertEqual(variant.kind, FotoVariant.KIND_FEED)
        with variant.image.open('rb') as fh:
            im = Image.open(fh)
            im.load()
        self.assertLessEqual(max(im.size), FEED_THUMB_MAX_SIDE)

    def test_signal_on_create(self):
        if Image is None:
            self.skipTest('Pillow not installed')
        foto = Foto.objects.create(
            title='Signal thumb',
            author=self.user,
            topic=self.topic,
            image=_large_jpeg_upload(),
        )
        self.assertTrue(
            FotoVariant.objects.filter(pin=pin, kind=FotoVariant.KIND_FEED).exists()
        )
