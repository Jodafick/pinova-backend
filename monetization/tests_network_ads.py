from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Profile


@override_settings(
    ADSENSE_CLIENT_ID='ca-pub-test',
    ADSENSE_SLOT_FEED='111',
    ADSENSE_SLOT_DETAIL='222',
    ADMOB_APP_ID_ANDROID='ca-app-pub-test~android',
    ADMOB_UNIT_FEED_ANDROID='ca-app-pub-test/banner',
)
class NetworkAdConfigViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='plususer', password='x')
        profile = self.user.profile
        profile.subscription_plan = Profile.PLAN_PLUS
        profile.ad_ads_enabled = True
        profile.save(update_fields=['subscription_plan', 'ad_ads_enabled'])

    def test_anonymous_sees_ads_when_configured(self):
        res = self.client.get('/api/monetization/network-ad-config/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['enabled'])
        self.assertTrue(body['configured'])
        self.assertTrue(body['show'])
        self.assertEqual(body['web']['client_id'], 'ca-pub-test')

    def test_plus_user_hides_network_ads(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get('/api/monetization/network-ad-config/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body['enabled'])
        self.assertFalse(body['show'])
        self.assertTrue(body['configured'])

    def test_pro_user_hides_network_ads(self):
        profile = self.user.profile
        profile.subscription_plan = Profile.PLAN_PRO
        profile.save(update_fields=['subscription_plan'])
        self.client.force_authenticate(user=self.user)
        res = self.client.get('/api/monetization/network-ad-config/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body['enabled'])
        self.assertFalse(body['show'])

    @override_settings(
        ADSENSE_CLIENT_ID='',
        ADSENSE_SLOT_FEED='',
        ADSENSE_SLOT_DETAIL='',
        ADMOB_APP_ID_ANDROID='',
        ADMOB_UNIT_FEED_ANDROID='',
        ADMOB_APP_ID_IOS='',
        ADMOB_UNIT_FEED_IOS='',
    )
    def test_not_configured_hides_ads(self):
        res = self.client.get('/api/monetization/network-ad-config/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body['configured'])
        self.assertFalse(body['show'])
