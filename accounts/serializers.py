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
            'private_profile',
            'notifications_followers',
            'notifications_saves',
            'notifications_recommendations',
            'subscription_cancel_at_period_end',
            'subscription_scheduled_plan',
            'share_token',
            'birth_date',
        ]
        read_only_fields = ['username', 'email', 'followers_count', 'following_count', 'is_following', 'country_code']

    _PUBLIC_PROFILE_HIDDEN_FIELDS = frozenset({
        'email',
        'subscription_renewal_at',
        'subscription_cancel_at_period_end',
        'subscription_scheduled_plan',
        'translation_quota_monthly',
        'translation_used_monthly',
        'ad_ads_enabled',
        'partner_ads_enabled',
        'notifications_followers',
        'notifications_saves',
        'notifications_recommendations',
        'share_token',
    })

    _OWNER_ONLY_FIELDS = frozenset({'birth_date'})

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        is_owner = viewer and viewer.is_authenticated and viewer.id == instance.user_id
        if not is_owner:
            for key in self._OWNER_ONLY_FIELDS:
                data.pop(key, None)
        if not is_owner:
            for key in self._PUBLIC_PROFILE_HIDDEN_FIELDS:
                data.pop(key, None)
        return data


from django.db.models import Prefetch

from pins.models import Save
from pins.models import Board, PinBoard, Pin
from pins.visibility import pin_is_visible_for_request


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    saved_pins = serializers.SerializerMethodField()
    boards = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'profile', 'saved_pins', 'boards', 'subscription']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        is_owner = viewer and viewer.is_authenticated and viewer.id == instance.id
        if not is_owner:
            data.pop('email', None)
        return data

    def get_saved_pins(self, obj):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        if not (viewer and viewer.is_authenticated and viewer.id == obj.id):
            return []
        return list(Save.objects.filter(user=obj).values_list('pin_id', flat=True))

    def get_boards(self, obj):
        request = self.context.get('request')
        owner_view = bool(request and request.user.is_authenticated and request.user == obj)
        boards = Board.objects.filter(user=obj)
        if not owner_view:
            boards = boards.filter(is_private=False)
        boards = boards.prefetch_related(
            Prefetch(
                'pins',
                queryset=Pin.objects.select_related('author', 'author__profile'),
            )
        ).order_by('-created_at')

        def visible_pin_count(board_obj):
            return sum(
                1 for p in board_obj.pins.all() if pin_is_visible_for_request(p, request)
            )

        def preview_for(board_obj):
            urls = []
            for row in (
                PinBoard.objects.filter(board=board_obj)
                .select_related('pin', 'pin__author', 'pin__author__profile')
                .order_by('position', 'id')
            ):
                if not pin_is_visible_for_request(row.pin, request):
                    continue
                img = getattr(row.pin, 'image', None)
                if not img or not getattr(img, 'name', None):
                    continue
                url = img.url
                urls.append(request.build_absolute_uri(url) if request else url)
                if len(urls) >= 6:
                    break
            return urls

        rows_out = []
        for board in boards:
            row = {
                'id': board.id,
                'name': board.name,
                'pinCount': visible_pin_count(board),
                'isPrivate': board.is_private,
                'previewImages': preview_for(board),
                'collaboratorCount': board.collaborators.count(),
            }
            if owner_view and board.share_token:
                row['share_token'] = str(board.share_token)
            rows_out.append(row)
        return rows_out

    def get_subscription(self, obj):
        profile = obj.profile
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        is_owner = viewer and viewer.is_authenticated and viewer.id == obj.id
        if not is_owner:
            return {'plan': profile.subscription_plan}
        return {
            'plan': profile.subscription_plan,
            'renewal_at': profile.subscription_renewal_at,
            'translation_quota_monthly': profile.translation_quota_monthly,
            'translation_used_monthly': profile.translation_used_monthly,
            'ad_ads_enabled': profile.ad_ads_enabled,
            'partner_ads_enabled': profile.partner_ads_enabled,
            'tips_enabled': profile.tips_enabled,
            'tips_url': profile.tips_url,
            'cancel_at_period_end': profile.subscription_cancel_at_period_end,
            'scheduled_plan': profile.subscription_scheduled_plan or None,
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
            title='Bienvenue sur PINOVA',
            message="Votre compte a été créé avec succès. Veuillez entrer le code OTP envoyé par email pour le valider.",
            action_url='/verify-otp',
            metadata={'stage': 'account_created_pending_verification'},
        )

        send_mail(
            'Code de validation PINOVA',
            f'Votre code de validation est : {otp.otp_code}. Il expire dans 10 minutes.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return user
