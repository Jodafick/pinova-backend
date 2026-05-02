from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, EmailOTP
from dj_rest_auth.registration.serializers import RegisterSerializer as BaseRegisterSerializer
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .currency_utils import normalize_currency

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'id',
            'username',
            'email',
            'display_name',
            'bio',
            'avatar',
            'avatar_color',
            'followers_count',
            'following_count',
            'is_following',
            'subscription_plan',
            'subscription_renewal_at',
            'translation_quota_monthly',
            'translation_used_monthly',
            'discoverable_profile',
            'allow_ai_translation',
            'preferred_language',
            'preferred_currency',
            'country_code',
            'ad_ads_enabled',
            'partner_ads_enabled',
            'tips_enabled',
            'tips_url',
        ]
        read_only_fields = ['username', 'email', 'followers_count', 'following_count', 'is_following', 'country_code']

    def validate_preferred_currency(self, value):
        normalized = normalize_currency(value)
        if not normalized:
            raise serializers.ValidationError('Unsupported currency code')
        return normalized

    def get_followers_count(self, obj):
        return obj.followers.count()

    def get_following_count(self, obj):
        return obj.following.count()

    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Check if current user follows this profile
            return request.user.profile.following.filter(id=obj.id).exists()
        return False

from pins.models import Save
from pins.models import Board

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    saved_pins = serializers.SerializerMethodField()
    boards = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'profile', 'saved_pins', 'boards', 'subscription']

    def get_saved_pins(self, obj):
        return list(Save.objects.filter(user=obj).values_list('pin_id', flat=True))

    def get_boards(self, obj):
        request = self.context.get('request')
        boards = Board.objects.filter(user=obj)
        if not (request and request.user.is_authenticated and request.user == obj):
            boards = boards.filter(is_private=False)
        boards = boards.order_by('-created_at')
        return [
            {
                'id': board.id,
                'name': board.name,
                'pinCount': board.pin_count,
                'isPrivate': board.is_private,
            }
            for board in boards
        ]

    def get_subscription(self, obj):
        profile = obj.profile
        return {
            'plan': profile.subscription_plan,
            'renewal_at': profile.subscription_renewal_at,
            'translation_quota_monthly': profile.translation_quota_monthly,
            'translation_used_monthly': profile.translation_used_monthly,
            'ad_ads_enabled': profile.ad_ads_enabled,
            'partner_ads_enabled': profile.partner_ads_enabled,
            'tips_enabled': profile.tips_enabled,
            'tips_url': profile.tips_url,
        }

class RegisterSerializer(BaseRegisterSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    display_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        # Si le username n'est pas fourni, on prend le début de l'email
        email = data.get('email')
        if not data.get('username') and email:
            data['username'] = email.split('@')[0]
            
        return super().validate(data)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data['display_name'] = self.validated_data.get('display_name', '')
        return data

    def save(self, request):
        user = super().save(request)
        display_name = self.cleaned_data.get('display_name')
        if display_name:
            profile = user.profile
            profile.display_name = display_name
            profile.save()
        
        # Générer et envoyer l'OTP
        otp, created = EmailOTP.objects.get_or_create(user=user, defaults={'expires_at': timezone.now() + timedelta(minutes=10)})
        otp.generate_otp()
        
        # Créer une notification de création de compte en attente de validation
        from notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='welcome',
            message="Votre compte a été créé avec succès. Veuillez entrer le code OTP envoyé par email pour le valider."
        )

        send_mail(
            'Code de validation PINOVA',
            f'Votre code de validation est : {otp.otp_code}. Il expire dans 10 minutes.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return user
