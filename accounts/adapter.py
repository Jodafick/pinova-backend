import logging
from datetime import date

import requests
from django.core.files.base import ContentFile

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialToken

from .models import Profile

logger = logging.getLogger(__name__)

# Langues UI Pinova (i18n) — autres codes Google ignorés pour éviter valeurs invalides.
_GOOGLE_LOCALE_TO_APP = frozenset({'fr', 'en', 'es', 'de', 'it', 'pt', 'ar', 'ja', 'zh'})
_PROFILE_LANGUAGE_DEFAULT = 'fr'


def _normalize_google_locale(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ''
    base = raw.strip().replace('_', '-').split('-')[0].lower()
    return base if base in _GOOGLE_LOCALE_TO_APP else ''


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

    def _google_access_token(self, sociallogin) -> str:
        tok = getattr(sociallogin, 'token', None)
        if tok is not None:
            secret = getattr(tok, 'token', None) or ''
            if secret:
                return secret
        account = getattr(sociallogin, 'account', None)
        if account and getattr(account, 'pk', None):
            st = SocialToken.objects.filter(account=account).order_by('-expires_at').first()
            if st and st.token:
                return st.token
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

    def _sync_google_people_fields(self, user: User, sociallogin) -> None:
        """People API : anniversaire (si vide) + langue (scope profile.language.read), un seul GET."""
        if sociallogin.account.provider != 'google':
            return
        profile = Profile.objects.filter(user=user).first()
        if not profile:
            return
        access = self._google_access_token(sociallogin)
        if not access:
            return
        try:
            r = requests.get(
                'https://people.googleapis.com/v1/people/me',
                params={'personFields': 'birthdays,locales'},
                headers={'Authorization': f'Bearer {access}'},
                timeout=15,
            )
            if r.status_code != 200:
                logger.debug('People API me status=%s pour %s', r.status_code, user.username)
                return
            payload = r.json()
        except Exception as exc:
            logger.debug('People API me indisponible pour %s: %s', user.username, exc)
            return

        update_fields: list[str] = []

        # --- Anniversaire (user.birthday.read) : ne remplit que si encore vide ---
        if not profile.birth_date:
            birthdays = payload.get('birthdays') or []
            chosen_bd = None
            for item in birthdays:
                if not isinstance(item, dict):
                    continue
                meta = item.get('metadata') or {}
                if meta.get('primary'):
                    chosen_bd = item
                    break
            if chosen_bd is None and birthdays and isinstance(birthdays[0], dict):
                chosen_bd = birthdays[0]
            if chosen_bd:
                d = chosen_bd.get('date') or {}
                try:
                    year = int(d.get('year'))
                    month = int(d.get('month'))
                    day_num = int(d.get('day'))
                    birth = date(year, month, day_num)
                    profile.birth_date = birth
                    update_fields.append('birth_date')
                except (TypeError, ValueError):
                    pass

        # --- Langue (profile.language.read) : si profil encore au défaut constructeur « fr » ---
        google_lang = ''
        locales = payload.get('locales') or []
        chosen_loc = None
        for item in locales:
            if not isinstance(item, dict):
                continue
            meta = item.get('metadata') or {}
            if meta.get('primary'):
                chosen_loc = item
                break
        if chosen_loc is None and locales and isinstance(locales[0], dict):
            chosen_loc = locales[0]
        if chosen_loc:
            google_lang = _normalize_google_locale(chosen_loc.get('value') or '')
        if (
            google_lang
            and profile.preferred_language == _PROFILE_LANGUAGE_DEFAULT
            and google_lang != profile.preferred_language
        ):
            profile.preferred_language = google_lang
            update_fields.append('preferred_language')

        if update_fields:
            profile.save(update_fields=update_fields)

    def _sync_google_profile_fields(self, user: User, sociallogin) -> None:
        self._sync_google_avatar(user, sociallogin)
        self._sync_google_people_fields(user, sociallogin)

    def _get_social_email(self, sociallogin):
        # Google peut renvoyer l'email dans user.email ou extra_data selon le flow OAuth.
        extra = sociallogin.account.extra_data or {}
        email_extra = extra.get('email', '') if isinstance(extra, dict) else ''
        return (sociallogin.user.email or email_extra or '').strip()

    def pre_social_login(self, request, sociallogin):
        # Si le compte social est déjà lié, allauth gère la connexion directement.
        if sociallogin.is_existing:
            self._sync_google_profile_fields(sociallogin.user, sociallogin)
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
            return

        # Nouveau compte: normaliser l'email avant création automatique.
        sociallogin.user.email = email

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        if user.email:
            EmailAddress.objects.update_or_create(
                user=user,
                email=user.email,
                defaults={'verified': True, 'primary': True},
            )
        self._sync_google_profile_fields(user, sociallogin)
        return user
