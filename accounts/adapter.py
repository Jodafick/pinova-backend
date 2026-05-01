from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from allauth.account.models import EmailAddress

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
    def _get_social_email(self, sociallogin):
        # Google peut renvoyer l'email dans user.email ou extra_data selon le flow OAuth.
        return (sociallogin.user.email or sociallogin.account.extra_data.get('email') or '').strip()

    def pre_social_login(self, request, sociallogin):
        # Si le compte social est déjà lié, allauth gère la connexion directement.
        if sociallogin.is_existing:
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
        return user
