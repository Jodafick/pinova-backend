"""Tests RGPD — export, consentement, mineurs, suppression."""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.age_policy import MIN_REGISTRATION_AGE, profile_is_minor_teen
from accounts.gdpr_export import build_user_export_bundle
from accounts.models import DataExportJob, Profile, UserConsent


class AgePolicyTests(TestCase):
    def test_rejects_under_13_on_profile_patch(self):
        user = User.objects.create_user('kid', 'kid@test.io', 'Passw0rd!123')
        client = APIClient()
        client.force_authenticate(user=user)
        too_young = date.today().replace(year=date.today().year - (MIN_REGISTRATION_AGE - 1))
        res = client.patch('http://testserver/api/me/', {'birth_date': too_young.isoformat()}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_teen_flag_13_17(self):
        user = User.objects.create_user('teen', 'teen@test.io', 'Passw0rd!123')
        profile = user.profile
        profile.birth_date = date.today().replace(year=date.today().year - 15)
        profile.save()
        self.assertTrue(profile_is_minor_teen(profile))


class ConsentApiTests(TestCase):
    def test_anonymous_consent_stored(self):
        client = APIClient()
        res = client.post(
            '/api/account/consent/',
            {'necessary': True, 'analytics': False, 'anonymous_id': 'anon-e2e-1'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['analytics'])
        self.assertTrue(UserConsent.objects.filter(anonymous_id='anon-e2e-1').exists())

    def test_authenticated_consent(self):
        user = User.objects.create_user('u1', 'u1@test.io', 'Passw0rd!123')
        client = APIClient()
        client.force_authenticate(user=user)
        res = client.post(
            '/api/account/consent/',
            {'necessary': True, 'analytics': True, 'anonymous_id': 'anon-auth'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        consent = UserConsent.objects.get(user=user)
        self.assertTrue(consent.analytics)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ExportApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('export', 'export@test.io', 'Passw0rd!123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('accounts.gdpr_views.send_fotoce_mail')
    def test_export_data_creates_job_and_zip(self, mock_mail):
        res = self.client.post('/api/account/export-data/', {}, format='json')
        self.assertEqual(res.status_code, 202)
        job = DataExportJob.objects.get(user=self.user)
        self.assertEqual(job.status, DataExportJob.STATUS_READY)
        self.assertTrue(job.file_path)
        mock_mail.assert_called()

        bundle = build_user_export_bundle(self.user)
        self.assertIn('profile', bundle)
        self.assertIn('fotos', bundle)

        dl = self.client.get(f'/api/account/export-download/{job.download_token}/')
        self.assertEqual(dl.status_code, 200)
        zf = ZipFile(BytesIO(b''.join(dl.streaming_content)))
        self.assertIn('fotoce-export.json', zf.namelist())


class AccountDeletionGdprTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('del', 'del@test.io', 'Passw0rd!123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('accounts.gdpr_views.send_fotoce_mail')
    @patch('accounts.gdpr_views._queue_export')
    def test_deletion_sends_email_and_optional_export(self, mock_queue, mock_mail):
        mock_queue.return_value = DataExportJob.objects.create(
            user=self.user,
            status=DataExportJob.STATUS_PENDING,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        res = self.client.post(
            '/api/account/deletion/request/',
            {'confirm': 'DELETE', 'request_export': True},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertIsNotNone(self.user.profile.account_scheduled_deletion_at)
        mock_queue.assert_called_once()
        self.assertGreaterEqual(mock_mail.call_count, 1)

    @patch('accounts.gdpr_views.send_fotoce_mail')
    def test_me_deletion_alias(self, mock_mail):
        res = self.client.post('/api/me/account-deletion/request/', {'confirm': 'SUPPRIMER'}, format='json')
        self.assertEqual(res.status_code, 200)
        mock_mail.assert_called_once()


class TeenPublishRestrictionTests(TestCase):
    def test_teen_cannot_create_pin(self):
        user = User.objects.create_user('teenpub', 'teenpub@test.io', 'Passw0rd!123')
        profile = user.profile
        profile.birth_date = date.today().replace(year=date.today().year - 14)
        profile.save()
        client = APIClient()
        client.force_authenticate(user=user)
        res = client.post(
            '/api/fotos/',
            {
                'title': 'Test',
                'description': '',
                'topic': 'General',
                'visibility': 'public',
                'is_story': 'false',
                'author': user.id,
            },
            format='multipart',
        )
        self.assertEqual(res.status_code, 400)
