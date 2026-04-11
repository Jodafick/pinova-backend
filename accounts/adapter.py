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
    def pre_social_login(self, request, sociallogin):
        # Si l'utilisateur est déjà connecté, on ne fait rien
        if sociallogin.is_existing:
            return

        # Vérifier si un utilisateur avec cet email existe déjà
        email = sociallogin.user.email
        if email:
            try:
                user = User.objects.get(email=email)
                # Lier le compte social au compte existant
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass
