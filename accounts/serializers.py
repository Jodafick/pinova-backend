from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from django.db import transaction
from .models import Profile, EmailOTP, SubscriptionPayment, UserBlock
from dj_rest_auth.registration.serializers import RegisterSerializer as BaseRegisterSerializer
from dj_rest_auth.serializers import PasswordResetSerializer as DjPasswordResetSerializer
from django.conf import settings
from .mail_delivery import (
    EMAIL_DELIVERY_ERROR_CODE,
    EMAIL_DELIVERY_USER_MESSAGE,
    EmailDeliveryUnavailable,
    send_pinova_mail,
)
from django.utils import timezone
from datetime import timedelta
from .currency_utils import normalize_currency
from notifications.notification_i18n import create_localized_notification
from pinova_backend.media_cache import build_versioned_media_url
from pins.moderation import validate_clean_text_fields

ALLOWED_ACCENT_COLORS = frozenset({
    'rose', 'pink', 'violet', 'indigo', 'blue', 'cyan', 'emerald', 'amber', 'orange',
})
from .reference_data import get_allowed_interest_slugs
SOCIAL_LINK_KEYS = frozenset({
    'instagram', 'tiktok', 'github', 'linkedin', 'youtube', 'portfolio', 'twitter', 'facebook',
})


def _normalize_slug_list(value, allowed=None, max_items=32, max_len=48):
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError('Expected a list')
    out = []
    for item in value:
        slug = str(item).strip().lower()[:max_len]
        if not slug or slug in out:
            continue
        if allowed is not None and slug not in allowed:
            continue
        out.append(slug)
        if len(out) >= max_items:
            break
    return out


def _normalize_social_links(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError('Expected an object')
    out = {}
    for key, url in value.items():
        k = str(key).strip().lower()
        if k not in SOCIAL_LINK_KEYS:
            continue
        u = str(url).strip()
        if not u:
            continue
        if len(u) > 500:
            u = u[:500]
        out[k] = u
    return out


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    tips_internal_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'id',
            'username',
            'email',
            'display_name',
            'first_name',
            'last_name',
            'bio',
            'avatar',
            'cover_image',
            'avatar_color',
            'gender',
            'pronouns',
            'city',
            'website',
            'job_title',
            'school',
            'company',
            'phone',
            'interests',
            'followed_onboarding_creators',
            'theme_mode',
            'accent_color',
            'date_format',
            'timezone',
            'presence_status',
            'show_activity',
            'show_last_seen',
            'allow_dm',
            'allow_tags_mentions',
            'favorite_quote',
            'hobbies',
            'skills',
            'social_links',
            'onboarding_completed_at',
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
            'tips_enabled',
            'tips_internal_enabled',
            'private_profile',
            'notifications_followers',
            'notifications_saves',
            'notifications_recommendations',
            'notifications_digest_creator_weekly',
            'subscription_cancel_at_period_end',
            'subscription_scheduled_plan',
            'subscription_trial_consumed_at',
            'share_token',
            'birth_date',
            'sensitive_media_blur_by_default',
            'hide_sensitive_pins',
            'ad_ads_enabled',
            'partner_ads_enabled',
        ]
        read_only_fields = [
            'username', 'email', 'followers_count', 'following_count', 'is_following',
            'subscription_trial_consumed_at', 'onboarding_completed_at',
        ]

    _PUBLIC_PROFILE_HIDDEN_FIELDS = frozenset({
        'email',
        'phone',
        'followed_onboarding_creators',
        'onboarding_completed_at',
        'subscription_renewal_at',
        'subscription_cancel_at_period_end',
        'subscription_scheduled_plan',
        'subscription_trial_consumed_at',
        'translation_quota_monthly',
        'translation_used_monthly',
        'notifications_followers',
        'notifications_saves',
        'notifications_recommendations',
        'notifications_digest_creator_weekly',
        'sensitive_media_blur_by_default',
        'hide_sensitive_pins',
        'share_token',
        'show_activity',
        'show_last_seen',
        'allow_dm',
        'allow_tags_mentions',
        'theme_mode',
        'date_format',
        'timezone',
    })

    _OWNER_ONLY_FIELDS = frozenset({'birth_date'})

    def validate_preferred_currency(self, value):
        normalized = normalize_currency(value)
        if not normalized:
            raise serializers.ValidationError('Unsupported currency code')
        return normalized

    def validate_country_code(self, value):
        code = (value or '').strip().upper()[:2]
        return code

    def validate_accent_color(self, value):
        v = (value or 'rose').strip().lower()
        if v not in ALLOWED_ACCENT_COLORS:
            raise serializers.ValidationError('Unsupported accent color')
        return v

    def validate_interests(self, value):
        return _normalize_slug_list(value, allowed=get_allowed_interest_slugs())

    def validate_followed_onboarding_creators(self, value):
        return _normalize_slug_list(value, allowed=None, max_items=50)

    def validate_hobbies(self, value):
        return _normalize_slug_list(value, allowed=None, max_items=24)

    def validate_skills(self, value):
        return _normalize_slug_list(value, allowed=None, max_items=24)

    def validate_social_links(self, value):
        return _normalize_social_links(value)

    def validate(self, attrs):
        text_fields = {}
        for key in ('display_name', 'first_name', 'last_name', 'bio', 'city', 'job_title', 'school', 'company', 'favorite_quote', 'pronouns'):
            if key in attrs:
                text_fields[key] = attrs[key]
        if text_fields:
            validate_clean_text_fields(text_fields)
        return attrs

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

    def get_tips_internal_enabled(self, obj):
        return obj.subscription_plan == Profile.PLAN_PRO and bool(obj.tips_enabled)

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
        if request:
            if getattr(instance, 'avatar', None) and getattr(instance.avatar, 'name', None):
                data['avatar'] = build_versioned_media_url(request, instance.avatar)
            if getattr(instance, 'cover_image', None) and getattr(instance.cover_image, 'name', None):
                data['cover_image'] = build_versioned_media_url(request, instance.cover_image)
        data.pop('tips_url', None)
        return data


from django.db.models import Prefetch

from pins.models import Save
from pins.models import Board, PinBoard, Pin, ContentReport
from pins.visibility import pin_is_visible_for_request, count_pins_visible_on_profile


class UserBlockSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='blocked.username', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = UserBlock
        fields = ('id', 'username', 'display_name', 'created_at')

    def get_display_name(self, obj):
        p = getattr(obj.blocked, 'profile', None)
        if p and (p.display_name or '').strip():
            return (p.display_name or '').strip()
        return obj.blocked.username


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    saved_pins = serializers.SerializerMethodField()
    boards = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()
    pins_count = serializers.SerializerMethodField()
    blocked_usernames = serializers.SerializerMethodField()
    viewer_has_reported_profile = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'profile',
            'saved_pins',
            'boards',
            'subscription',
            'pins_count',
            'blocked_usernames',
            'viewer_has_reported_profile',
            'is_staff',
        ]

    def get_pins_count(self, obj):
        request = self.context.get('request')
        if request is None:
            return 0
        return count_pins_visible_on_profile(obj, request)

    def get_blocked_usernames(self, obj):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        if not viewer or not viewer.is_authenticated or viewer.id != obj.id:
            return []
        return list(
            UserBlock.objects.filter(blocker=viewer)
            .select_related('blocked')
            .order_by('-created_at')
            .values_list('blocked__username', flat=True),
        )

    def get_viewer_has_reported_profile(self, obj):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        if not viewer or not viewer.is_authenticated or viewer.id == obj.id:
            return False
        return ContentReport.objects.filter(reporter=viewer, reported_user=obj).exists()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        is_owner = viewer and viewer.is_authenticated and viewer.id == instance.id
        if not is_owner:
            data.pop('email', None)
        if is_owner:
            data.pop('viewer_has_reported_profile', None)
        return data

    def get_saved_pins(self, obj):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        if not (viewer and viewer.is_authenticated and viewer.id == obj.id):
            return []
        return list(Save.objects.filter(user=obj).values_list('pin_id', flat=True))

    def get_boards(self, obj):
        request = self.context.get('request')
        if self.context.get('omit_full_board_list'):
            return []
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
                urls.append(build_versioned_media_url(request, img) if request else img.url)
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
        sub = {
            'plan': profile.subscription_plan,
            'renewal_at': profile.subscription_renewal_at,
            'translation_quota_monthly': profile.translation_quota_monthly,
            'translation_used_monthly': profile.translation_used_monthly,
            'tips_enabled': profile.tips_enabled,
            'tips_url': profile.tips_url,
            'cancel_at_period_end': profile.subscription_cancel_at_period_end,
            'scheduled_plan': profile.subscription_scheduled_plan or None,
            'trial_consumed_at': profile.subscription_trial_consumed_at.isoformat()
            if profile.subscription_trial_consumed_at else None,
            'trial_eligible': (
                profile.subscription_plan == Profile.PLAN_FREE and profile.subscription_trial_consumed_at is None
            ),
            'digest_creator_weekly': profile.notifications_digest_creator_weekly,
            'account_scheduled_deletion_at': profile.account_scheduled_deletion_at.isoformat()
            if profile.account_scheduled_deletion_at
            else None,
            'seat_bundle': getattr(profile, 'subscription_seat_bundle', None) or 'solo',
            'is_seat_member': bool(getattr(profile, 'subscription_sponsor_id', None)),
            'sponsor_username': profile.subscription_sponsor.username
            if getattr(profile, 'subscription_sponsor_id', None)
            else None,
            'sensitive_media_blur_by_default': getattr(
                profile,
                'sensitive_media_blur_by_default',
                True,
            ),
            'hide_sensitive_pins': bool(getattr(profile, 'hide_sensitive_pins', False)),
            'ad_ads_enabled': bool(getattr(profile, 'ad_ads_enabled', True)),
            'partner_ads_enabled': bool(getattr(profile, 'partner_ads_enabled', True)),
        }
        from .subscription_seats import max_invitees_for_bundle, owner_eligible_as_seat_hub

        if owner_eligible_as_seat_hub(profile):
            sub['seat_max_invitees'] = max_invitees_for_bundle(profile.subscription_seat_bundle)
        last_pay_cycle = (
            SubscriptionPayment.objects.filter(user=obj, status=SubscriptionPayment.STATUS_APPROVED)
            .order_by('-created_at')
            .values_list('billing_cycle', flat=True)
            .first()
        )
        sub['active_billing_cycle'] = last_pay_cycle or None
        sub['has_billing_history'] = SubscriptionPayment.objects.filter(user=obj).exists()
        return sub


class SetInitialPasswordSerializer(serializers.Serializer):
    """Mot de passe initial pour comptes créés via réseau social (sans mot de passe Django)."""

    new_password1 = serializers.CharField(write_only=True)
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': _('Les mots de passe ne correspondent pas.')})
        user = self.context['request'].user
        try:
            validate_password(attrs['new_password1'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password1': list(exc.messages)})
        return attrs


class RegisterSerializer(BaseRegisterSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    display_name = serializers.CharField(required=False, allow_blank=True)
    referral_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, data):
        # Si le username n'est pas fourni, on prend le début de l'email
        email = data.get('email')
        if not data.get('username') and email:
            data['username'] = email.split('@')[0]
        validate_clean_text_fields(
            {
                'username': str(data.get('username', '') or ''),
                'display_name': str(data.get('display_name', '') or ''),
            },
            message='Ce champ contient un contenu inapproprie. Merci de le modifier.',
        )
        return super().validate(data)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data['display_name'] = self.validated_data.get('display_name', '')
        return data

    def save(self, request):
        with transaction.atomic():
            user = super().save(request)
            from referrals.fraud_engine import record_signup_context

            record_signup_context(user, request)
            display_name = self.cleaned_data.get('display_name')
            if display_name:
                profile = user.profile
                profile.display_name = display_name
                profile.save()

            # Générer et envoyer l'OTP
            otp, created = EmailOTP.objects.get_or_create(
                user=user, defaults={'expires_at': timezone.now() + timedelta(minutes=10)}
            )
            otp.generate_otp()

            # Créer une notification de création de compte en attente de validation
            create_localized_notification(
                recipient=user,
                notification_type='welcome',
                title_fr='Bienvenue sur PINOVA',
                message_fr="Votre compte a été créé avec succès. Veuillez entrer le code OTP envoyé par email pour le valider.",
                action_url='/verify-otp',
                metadata={'stage': 'account_created_pending_verification'},
            )

            try:
                send_pinova_mail(
                    'Code de validation PINOVA',
                    f'Votre code de validation est : {otp.otp_code}. Il expire dans 10 minutes.',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except EmailDeliveryUnavailable:
                raise ValidationError(
                    {
                        'non_field_errors': [EMAIL_DELIVERY_USER_MESSAGE],
                        'code': [EMAIL_DELIVERY_ERROR_CODE],
                    }
                ) from None

            from referrals.services import consume_referral_for_new_user

            device = (request.META.get('HTTP_X_PINOVA_DEVICE_BINDING') or '').strip() if request else ''
            consume_referral_for_new_user(
                user,
                explicit_code=self.validated_data.get('referral_code'),
                request=request,
                device_binding_header=device or None,
            )
        return user


class PinovaLoginSerializer(serializers.Serializer):
    """
    Connexion JWT : distingue « e-mail inconnu » vs « mot de passe incorrect » pour l'UX.
    (Énumération d'e-mails : assumée côté produit.)
    """

    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    CODE_UNKNOWN_EMAIL = 'pinova_login_unknown_email'
    CODE_WRONG_PASSWORD = 'pinova_login_wrong_password'
    CODE_INACTIVE = 'pinova_login_inactive'
    CODE_EMAIL_UNVERIFIED = 'pinova_login_email_unverified'

    def validate(self, attrs):
        from dj_rest_auth.serializers import LoginSerializer as _dj_login_serializer

        username = (attrs.get('username') or '').strip()
        email_raw = (attrs.get('email') or '').strip()
        if not email_raw and username:
            email_raw = username
        email_norm = email_raw.lower()
        password = attrs.get('password') or ''

        if not email_norm or not password:
            raise serializers.ValidationError(_('Must include "email" and "password".'))

        user = User.objects.filter(email__iexact=email_norm).first()
        if not user:
            user = User.objects.filter(username__iexact=email_norm).first()
        if not user:
            raise serializers.ValidationError({'email': [self.CODE_UNKNOWN_EMAIL]})

        if not user.check_password(password):
            raise serializers.ValidationError({'password': [self.CODE_WRONG_PASSWORD]})

        if not user.is_active:
            raise serializers.ValidationError({'non_field_errors': [self.CODE_INACTIVE]})

        if 'dj_rest_auth.registration' in settings.INSTALLED_APPS:
            try:
                _dj_login_serializer.validate_email_verification_status(user, email=email_raw)
            except serializers.ValidationError:
                raise serializers.ValidationError({'email': [self.CODE_EMAIL_UNVERIFIED]}) from None

        attrs['user'] = user
        return attrs


def pinova_password_reset_url_generator(request, user, temp_key):
    """
    Lien de reset aligné sur le routeur web (`/password-reset-confirm/:uid/:token`).
    Évite `NoReverseMatch` sur `password_reset_confirm` (non défini avec dj-rest-auth seul).
    """
    from urllib.parse import quote
    from allauth.account.utils import user_pk_to_url_str

    base = (getattr(settings, 'URL_FRONTEND_PASSWORD_RESET', None) or '').strip().rstrip('/')
    if not base:
        base = settings.FRONTEND_URL.rstrip('/') + '/password-reset-confirm'
    uid = user_pk_to_url_str(user)
    return f'{base}/{quote(uid, safe="")}/{quote(temp_key, safe="")}'


class PinovaPasswordResetSerializer(DjPasswordResetSerializer):
    """Passe un `url_generator` qui pointe vers le SPA au lieu de `reverse('password_reset_confirm')`."""

    def get_email_options(self):
        opts = super().get_email_options()
        opts['url_generator'] = pinova_password_reset_url_generator
        return opts
