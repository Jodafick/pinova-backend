import logging

import requests
from django.core.files.base import ContentFile

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from allauth.account.models import EmailAddress

from .models import Profile

logger = logging.getLogger(__name__)


class NoEmailConfirmationAdapter(DefaultAccountAdapter):
    # ... (vos méthodes existantes)
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        pass

    def send_account_already_exists_mail(self, email):
        pass

    def get_signup_url(self, request):
        from django.conf import settings
        return getattr(settings, 'FRONTEND_URL', 'http://localhost:5174') + '/register'

    def get_login_url(self, request):
        from django.conf import settings
        return getattr(settings, 'FRONTEND_URL', 'http://localhost:5174') + '/login'


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def _ensure_social_login_email_verified(self, user: User, sociallogin) -> None:
        """
        Google / Facebook attestent l’e-mail : la marquer vérifiée dans allauth (connexion existante ou liaison).
        Les nouveaux comptes passent aussi par ici via ``save_user``.
        """
        provider = (getattr(sociallogin.account, 'provider', None) or '').strip().lower()
        if provider not in ('google', 'facebook'):
            return
        email = (getattr(user, 'email', None) or self._get_social_email(sociallogin) or '').strip()
        if not email:
            return
        EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={'verified': True, 'primary': True},
        )

    def _google_picture_url(self, sociallogin) -> str:
        """URL photo profil Google depuis les données renvoyées par le provider (scope profile)."""
        if sociallogin.account.provider != 'google':
            return ''
        extra = sociallogin.account.extra_data or {}
        if not isinstance(extra, dict):
            return ''
        url = (extra.get('picture') or '').strip()
        if url:
            return url
        user_block = extra.get('user')
        if isinstance(user_block, dict):
            return (user_block.get('picture') or '').strip()
        return ''

    def _sync_google_avatar(self, user: User, sociallogin) -> None:
        """Met à jour l’avatar depuis la photo Google si une URL est disponible (scope profile)."""
        if sociallogin.account.provider != 'google':
            return
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
            return
        url = self._google_picture_url(sociallogin)
        if not url:
            return
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200 or not resp.content:
                return
            ctype = (resp.headers.get('Content-Type') or '').lower()
            ext = '.jpg'
            if 'png' in ctype:
                ext = '.png'
            elif 'webp' in ctype:
                ext = '.webp'
            elif 'gif' in ctype:
                ext = '.gif'
            fname = f'google_avatar_{user.pk}{ext}'
            profile.avatar.save(fname, ContentFile(resp.content), save=True)
        except Exception as exc:
            logger.debug('Avatar Google non importé pour %s: %s', user.username, exc)

    def _sync_google_profile_fields(self, user: User, sociallogin) -> None:
        self._sync_google_avatar(user, sociallogin)

    def _get_social_email(self, sociallogin):
        # Google peut renvoyer l'email dans user.email ou extra_data selon le flow OAuth.
        extra = sociallogin.account.extra_data or {}
        email_extra = extra.get('email', '') if isinstance(extra, dict) else ''
        return (sociallogin.user.email or email_extra or '').strip()

    def pre_social_login(self, request, sociallogin):
        # Si le compte social est déjà lié, allauth gère la connexion directement.
        if sociallogin.is_existing:
            self._sync_google_profile_fields(sociallogin.user, sociallogin)
            self._ensure_social_login_email_verified(sociallogin.user, sociallogin)
            return

        # Comportement voulu:
        # - compte existant => connexion
        # - compte inexistant => création puis connexion
        email = self._get_social_email(sociallogin)
        if not email:
            return

        existing_user = User.objects.filter(email__iexact=email).order_by('id').first()
        if existing_user:
            sociallogin.connect(request, existing_user)
            self._sync_google_profile_fields(existing_user, sociallogin)
            self._ensure_social_login_email_verified(existing_user, sociallogin)
            return

        # Nouveau compte: normaliser l'email avant création automatique.
        sociallogin.user.email = email

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        self._ensure_social_login_email_verified(user, sociallogin)
        self._sync_google_profile_fields(user, sociallogin)
        from referrals.fraud_engine import record_signup_context

        record_signup_context(user, request)
        from referrals.services import assign_referrer_from_registration_context

        assign_referrer_from_registration_context(user, request, sociallogin)
        return user
