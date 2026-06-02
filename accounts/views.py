from rest_framework import viewsets, status, permissions
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import requests
from django.db import transaction, IntegrityError, connection
from django.db.utils import NotSupportedError
import logging
from urllib.parse import urlparse

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5174') + "/login"
    client_class = OAuth2Client

class FacebookLogin(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    callback_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5174') + "/login"
    client_class = OAuth2Client
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid
from .models import (
    MobileOAuthLoginCode,
    Profile,
    EmailOTP,
    SubscriptionPayment,
    SubscriptionPricing,
    SupportTicket,
    UserBlock,
)
from .subscription_utils import _enforce_subscription_state
from .subscription_seats import SUBSCRIPTION_FAMILY_MAX_INVITEES, SUBSCRIPTION_TEAM_MAX_INVITEES
from .blocking import blocked_mutual_user_ids, users_are_mutually_blocked
from pinova_backend.media_cache import build_versioned_media_url

from .serializers import (
    ProfileSerializer,
    UserSerializer,
    RegisterSerializer,
    UserBlockSerializer,
    SetInitialPasswordSerializer,
)
from .mail_delivery import (
    EMAIL_DELIVERY_ERROR_CODE,
    EMAIL_DELIVERY_USER_MESSAGE,
    EmailDeliveryUnavailable,
    send_pinova_mail,
)
from allauth.account.models import EmailAddress
from .currency_utils import (
    SUPPORTED_CURRENCIES,
    convert_minor_amount,
    decimals_for_currency,
    default_currency_for_country,
    infer_country_code,
    normalize_currency,
)

from .preference_utils import interest_slugs_for_user

logger = logging.getLogger(__name__)

MOBILE_GOOGLE_LOGIN_CODE_TTL_SECONDS = int(os.environ.get('MOBILE_GOOGLE_LOGIN_CODE_TTL_SECONDS', '120'))
MOBILE_GOOGLE_DEVICE_BINDING_MAX_LENGTH = 128
MOBILE_GOOGLE_STATE_MAX_LENGTH = 256


def _mobile_oauth_code_hash(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode('utf-8')).hexdigest()


def _mobile_device_binding(raw_value) -> str:
    value = str(raw_value or '').strip()
    if not value or len(value) > MOBILE_GOOGLE_DEVICE_BINDING_MAX_LENGTH:
        return ''
    return value


def _mobile_state(raw_value) -> str:
    value = str(raw_value or '').strip()
    if not value or len(value) > MOBILE_GOOGLE_STATE_MAX_LENGTH:
        return ''
    return value


_JSON_LIST_PATCH_KEYS = frozenset({
    'interests', 'followed_onboarding_creators', 'hobbies', 'skills', 'social_links',
})


def _patch_payload_from_request(request):
    """
    Dict plat pour ProfileSerializer.
    QueryDict convertit les listes Python en str() (quotes simples) → JSONField DRF invalide.
    """
    payload = {key: request.data.get(key) for key in request.data}
    for json_key in _JSON_LIST_PATCH_KEYS:
        if json_key not in payload:
            continue
        raw = payload[json_key]
        if isinstance(raw, list):
            payload[json_key] = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                payload[json_key] = json.loads(raw)
            except json.JSONDecodeError:
                return None, json_key
        elif raw in (None, ''):
            payload[json_key] = []
    return payload, None


def _users_with_shared_interests(queryset, interest_slugs, *, limit=24, prefetch=200):
    """Filtre par centres d'intérêt — fallback Python si JSON __contains indisponible (SQLite)."""
    slugs = [str(s).strip().lower() for s in interest_slugs[:16] if str(s).strip()]
    if not slugs:
        return []

    if connection.vendor == 'postgresql':
        interest_q = models.Q()
        for slug in slugs:
            interest_q |= models.Q(profile__interests__contains=[slug])
        try:
            return list(queryset.filter(interest_q).order_by('-followers_total', 'username')[:limit])
        except NotSupportedError:
            pass

    slug_set = set(slugs)
    pool = list(queryset.order_by('-followers_total', 'username')[:prefetch])
    matched = []
    for user in pool:
        raw = user.profile.interests
        user_interests = {str(x).strip().lower() for x in raw} if isinstance(raw, list) else set()
        if slug_set.intersection(user_interests):
            matched.append(user)
        if len(matched) >= limit:
            break
    return matched


def _is_allowed_mobile_google_redirect_uri(raw_uri: str) -> bool:
    try:
        parsed = urlparse(raw_uri)
        expected = urlparse(getattr(settings, 'FRONTEND_URL', 'http://localhost:5174').rstrip('/'))
    except Exception:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    return (
        parsed.scheme == expected.scheme
        and parsed.netloc == expected.netloc
        and parsed.path.rstrip('/') == '/auth/mobile/google'
    )


class MobileGoogleSessionStartView(GoogleLogin):
    """
    Échange le code OAuth Google côté backend, puis crée un code Pinova court.

    Le navigateur web ne renvoie jamais le token Google au deep link mobile :
    l'application reçoit seulement ce code à usage unique et l'échange contre
    les JWT Pinova via MobileGoogleSessionExchangeView.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        code = str(request.data.get('code') or '').strip()
        redirect_uri = str(request.data.get('redirect_uri') or '').strip()
        device_binding_id = _mobile_device_binding(request.data.get('device_binding_id'))
        mobile_state = _mobile_state(request.data.get('mobile_state'))
        if not code:
            return Response({'detail': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not redirect_uri or not _is_allowed_mobile_google_redirect_uri(redirect_uri):
            return Response({'detail': 'invalid redirect_uri'}, status=status.HTTP_400_BAD_REQUEST)
        if not device_binding_id:
            return Response({'detail': 'device_binding_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not mobile_state:
            return Response({'detail': 'mobile_state is required'}, status=status.HTTP_400_BAD_REQUEST)

        self.request = request
        self.callback_url = redirect_uri
        self.serializer = self.get_serializer(data={'code': code})
        self.serializer.is_valid(raise_exception=True)
        self.login()
        auth_response = self.get_response()
        auth_payload = dict(auth_response.data)
        if not auth_payload.get('access'):
            return Response({'detail': 'google login refused'}, status=status.HTTP_400_BAD_REQUEST)

        raw_mobile_code = secrets.token_urlsafe(32)
        now = timezone.now()
        MobileOAuthLoginCode.objects.filter(expires_at__lt=now).delete()
        MobileOAuthLoginCode.objects.create(
            code_hash=_mobile_oauth_code_hash(raw_mobile_code),
            device_binding_id=device_binding_id,
            mobile_state_hash=_mobile_oauth_code_hash(mobile_state),
            payload=auth_payload,
            expires_at=now + timedelta(seconds=MOBILE_GOOGLE_LOGIN_CODE_TTL_SECONDS),
        )
        return Response(
            {'code': raw_mobile_code, 'expires_in': MOBILE_GOOGLE_LOGIN_CODE_TTL_SECONDS},
            status=status.HTTP_201_CREATED,
        )


class MobileGoogleSessionExchangeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        raw_code = str(request.data.get('code') or '').strip()
        mobile_state = _mobile_state(request.data.get('mobile_state'))
        device_binding_id = _mobile_device_binding(request.META.get('HTTP_X_PINOVA_DEVICE_BINDING'))
        if not raw_code:
            return Response({'detail': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not mobile_state:
            return Response({'detail': 'mobile_state is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not device_binding_id:
            return Response({'detail': 'device binding is required'}, status=status.HTTP_400_BAD_REQUEST)

        code_hash = _mobile_oauth_code_hash(raw_code)
        with transaction.atomic():
            row = (
                MobileOAuthLoginCode.objects
                .select_for_update()
                .filter(code_hash=code_hash)
                .first()
            )
            if not row or not row.is_usable():
                return Response({'detail': 'invalid or expired code'}, status=status.HTTP_400_BAD_REQUEST)
            if (
                not row.device_binding_id
                or not hmac.compare_digest(row.device_binding_id, device_binding_id)
            ):
                return Response({'detail': 'invalid device binding'}, status=status.HTTP_400_BAD_REQUEST)
            expected_state_hash = row.mobile_state_hash or ''
            if not expected_state_hash or not hmac.compare_digest(
                expected_state_hash,
                _mobile_oauth_code_hash(mobile_state),
            ):
                return Response({'detail': 'invalid mobile state'}, status=status.HTTP_400_BAD_REQUEST)
            payload = dict(row.payload or {})
            row.consumed_at = timezone.now()
            row.payload = {}
            row.save(update_fields=['consumed_at', 'payload'])

        return Response(payload, status=status.HTTP_200_OK)


def _fedapay_normalize_transaction_body(body):
    """FedaPay peut renvoyer la transaction à la racine ou sous data / v1/transaction / transaction."""
    if not isinstance(body, dict):
        return {}
    data = body.get('data')
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if isinstance(data, dict):
        transaction_markers = ('status', 'id', 'amount', 'approved_at', 'reference', 'receipt_url')
        if any(k in data for k in transaction_markers):
            return data
    for key in ('v1/transaction', 'transaction'):
        nested = body.get(key)
        if isinstance(nested, dict) and any(k in nested for k in ('status', 'id', 'amount', 'approved_at')):
            return nested
    return body


def _fedapay_normalized_status(normalized):
    s = str((normalized or {}).get('status') or '').strip().lower()
    if s:
        return s
    if (normalized or {}).get('approved_at'):
        return 'approved'
    return ''


def _fedapay_webhook_transaction_id(payload):
    if not isinstance(payload, dict):
        return ''
    tid = str(payload.get('transaction_id') or payload.get('id') or '').strip()
    if tid:
        return tid
    for key in ('data', 'v1/transaction', 'transaction', 'entity'):
        block = payload.get(key)
        if isinstance(block, dict):
            tid = str(block.get('id') or block.get('transaction_id') or '').strip()
            if tid:
                return tid
        elif isinstance(block, list) and block and isinstance(block[0], dict):
            tid = str(block[0].get('id') or block[0].get('transaction_id') or '').strip()
            if tid:
                return tid
    return ''


def _fedapay_webhook_status(payload):
    """Lit le statut sur le corps webhook plat ou imbriqué."""
    if not isinstance(payload, dict):
        return ''
    direct = str(payload.get('status') or '').strip().lower()
    if direct:
        return direct
    for key in ('data', 'v1/transaction', 'transaction', 'entity'):
        block = payload.get(key)
        if isinstance(block, dict):
            st = _fedapay_normalized_status(block)
            if st:
                return st
        elif isinstance(block, list) and block and isinstance(block[0], dict):
            st = _fedapay_normalized_status(block[0])
            if st:
                return st
    return ''


def _fedapay_confirm_response_summary(raw_body, normalized):
    """Résumé court pour les logs (évite de logger tout le JSON FedaPay)."""
    summary = {}
    if isinstance(raw_body, dict):
        summary['raw_keys'] = sorted(raw_body.keys())[:30]
    if isinstance(normalized, dict):
        for k in ('id', 'status', 'amount', 'approved_at', 'currency', 'reference'):
            if normalized.get(k) is not None:
                summary[k] = normalized.get(k)
    return summary


def _normalize_url_path_slashes(url: str):
    value = (url or '').strip()
    if '://' not in value:
        return value
    scheme, rest = value.split('://', 1)
    rest = re.sub(r'/+', '/', rest)
    return f'{scheme}://{rest}'

def _catalog_entry(plan: str, billing_cycle: str, seat_bundle=None):
    bundle = _normalized_seat_bundle(seat_bundle)
    row = SubscriptionPricing.objects.filter(
        plan=plan,
        billing_cycle=billing_cycle,
        seat_bundle=bundle,
        is_active=True,
    ).first()
    if row:
        return {
            'amount': int(row.amount),
            'duration_days': int(row.duration_days),
            'currency_iso': row.currency_iso or os.environ.get('FEDAPAY_CURRENCY_ISO', 'XOF'),
            'source': 'backoffice',
        }
    return None


def _resolve_user_currency(request):
    if request.user.is_authenticated:
        profile = request.user.profile
        _enforce_subscription_state(profile)
        updates = []
        detected_country = infer_country_code(request)
        if not profile.country_code and detected_country:
            profile.country_code = detected_country
            updates.append('country_code')

        resolved_currency = normalize_currency(profile.preferred_currency)
        if not resolved_currency:
            resolved_currency = default_currency_for_country(profile.country_code or detected_country)
            profile.preferred_currency = resolved_currency
            updates.append('preferred_currency')

        if updates:
            profile.save(update_fields=updates)
        return resolved_currency, (profile.country_code or detected_country or '')

    detected_country = infer_country_code(request)
    return default_currency_for_country(detected_country), (detected_country or '')


def _display_amount(amount_minor: int, currency_iso: str):
    decimals = decimals_for_currency(currency_iso)
    return amount_minor / (10 ** decimals)


SUBSCRIPTION_BUNDLE_SOLO = 'solo'
SUBSCRIPTION_BUNDLE_FAMILY = 'family'
SUBSCRIPTION_BUNDLE_TEAM = 'team'


def _normalized_seat_bundle(raw) -> str:
    value = str(raw or '').strip().lower()
    if value == SUBSCRIPTION_BUNDLE_FAMILY:
        return SUBSCRIPTION_BUNDLE_FAMILY
    if value == SUBSCRIPTION_BUNDLE_TEAM:
        return SUBSCRIPTION_BUNDLE_TEAM
    return SUBSCRIPTION_BUNDLE_SOLO


def _fedapay_checkout_customer_names(user):
    """Prénom / nom pour les reçus FedaPay : priorité au nom affiché du profil, sans suffixe forcé « Pinova »."""
    profile = getattr(user, 'profile', None)
    display = (getattr(profile, 'display_name', None) or '').strip()
    if display:
        parts = display.split(None, 1)
        first_name = parts[0][:100]
        if len(parts) > 1:
            last_name = parts[1][:100].strip()
            return first_name, last_name
        ln = (getattr(user, 'last_name', None) or '').strip()[:100]
        if ln:
            return first_name, ln
        return first_name, '-'

    fn = (getattr(user, 'first_name', None) or '').strip()
    ln = (getattr(user, 'last_name', None) or '').strip()
    combined = f'{fn} {ln}'.strip()
    if combined and re.match(r'^pinova(\s|-|_|$)', combined, flags=re.I):
        rest = re.sub(r'^pinova[\s_-]*', '', combined, count=1, flags=re.I).strip()
        if rest:
            parts = rest.split(None, 1)
            return parts[0][:100], ((parts[1] if len(parts) > 1 else '-')[:100])
    if fn or ln:
        return (fn or user.username)[:100], (ln or '-')[:100]
    return (user.username or 'client')[:100], '-'


def _fedapay_checkout_description(plan: str, billing_cycle: str, seat_bundle: str) -> str:
    """Libellé transaction / reçu, formulation lisible côté client (évite tout en camelCase dans la description)."""
    plan_labels = {Profile.PLAN_PLUS: 'Pinova Plus', Profile.PLAN_PRO: 'Pinova Pro'}
    cycle_labels = {'monthly': 'facturation mensuelle', 'yearly': 'facturation annuelle'}
    bundle = _normalized_seat_bundle(seat_bundle)
    bundle_chunks = []
    if bundle == SUBSCRIPTION_BUNDLE_FAMILY:
        bundle_chunks.append('offre famille')
    elif bundle == SUBSCRIPTION_BUNDLE_TEAM:
        bundle_chunks.append('offre équipe')
    bits = ['Abonnement', plan_labels.get(plan, 'Pinova ' + plan.title())]
    bits.append(cycle_labels.get(billing_cycle, billing_cycle))
    bits.extend(bundle_chunks)
    return ' · '.join(bits)


def _plus_trial_duration_days() -> int:
    try:
        return max(1, min(90, int(os.environ.get('SUBSCRIPTION_PLUS_TRIAL_DAYS', '14'))))
    except ValueError:
        return 14


def _annual_discount_percent_display() -> int:
    from .models import PinovaSubscriptionConfig
    return int(PinovaSubscriptionConfig.load().annual_discount_percent)


def _extract_invoice_url_from_fedapay(normalized):
    """Tente de lire une URL de reçu / facture depuis la réponse FedaPay."""
    if not isinstance(normalized, dict):
        return ''

    def from_dict(d):
        direct_keys = (
            'invoice_url', 'invoice_pdf_url', 'receipt_url',
            'receipt_pdf_url', 'pdf_url', 'payment_proof_url',
        )
        for key in direct_keys:
            val = d.get(key)
            if isinstance(val, str) and val.startswith('http'):
                return val[:500]
        receipt = d.get('receipt')
        if isinstance(receipt, dict):
            for key in ('url', 'pdf_url', 'download_url', 'invoice_url'):
                val = receipt.get(key)
                if isinstance(val, str) and val.startswith('http'):
                    return val[:500]
        return ''

    url = from_dict(normalized)
    if url:
        return url
    nested = normalized.get('transaction')
    if isinstance(nested, dict):
        return from_dict(nested)
    return ''


def _subscription_catalog(target_currency: str, seat_bundle: str = SUBSCRIPTION_BUNDLE_SOLO):
    target = normalize_currency(target_currency) or 'XOF'
    bundle_normalized = _normalized_seat_bundle(seat_bundle)
    plans = (Profile.PLAN_FREE, Profile.PLAN_PLUS, Profile.PLAN_PRO)
    cycles = (SubscriptionPayment.BILLING_MONTHLY, SubscriptionPayment.BILLING_YEARLY)
    data = {}
    for plan in plans:
        data[plan] = {}
        for cycle in cycles:
            if plan == Profile.PLAN_FREE:
                duration_days = 30 if cycle == SubscriptionPayment.BILLING_MONTHLY else 365
                data[plan][cycle] = {
                    'amount_minor': 0,
                    'amount_display': _display_amount(0, target),
                    'currency_iso': target,
                    'duration_days': duration_days,
                    'source': 'system_free',
                    'base_amount_minor': 0,
                    'base_currency_iso': target,
                    'seat_bundle': bundle_normalized,
                    'bundle_discount_fraction': 0.0,
                }
                continue
            values = _catalog_entry(plan, cycle, bundle_normalized)
            if not values:
                continue
            amount = int(values['amount'])
            duration_days = int(values['duration_days'])
            base_currency = (values.get('currency_iso') or os.environ.get('FEDAPAY_CURRENCY_ISO', 'XOF')).upper()
            converted_amount = convert_minor_amount(amount, base_currency, target)
            effective_currency = target
            effective_amount = converted_amount
            conversion_applied = True
            if converted_amount is None:
                effective_currency = base_currency
                effective_amount = amount
                conversion_applied = False
            effective_minor = int(effective_amount)
            data[plan][cycle] = {
                'amount_minor': effective_minor,
                'amount_display': _display_amount(effective_minor, effective_currency),
                'currency_iso': effective_currency,
                'duration_days': duration_days,
                'source': values.get('source', 'unknown'),
                'base_amount_minor': amount,
                'base_currency_iso': base_currency,
                'conversion_applied': conversion_applied,
                'seat_bundle': bundle_normalized,
                'bundle_discount_fraction': 0.0,
            }
    return data


class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        otp_code = request.data.get('otp')

        if not email or not otp_code:
            return Response({'error': 'Email et code OTP requis'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            otp = EmailOTP.objects.get(user=user, otp_code=otp_code)

            if otp.is_expired():
                return Response({'error': 'Code OTP expiré'}, status=status.HTTP_400_BAD_REQUEST)

            email_address, created = EmailAddress.objects.get_or_create(
                user=user,
                email=email,
                defaults={'verified': True, 'primary': True}
            )
            if not email_address.verified:
                email_address.verified = True
                email_address.save()

            create_localized_notification(
                recipient=user,
                notification_type='welcome',
                title_fr='Compte valide',
                message_fr=f"Bienvenue sur PINOVA, {user.username} ! Votre compte est maintenant validé.",
                action_url='/',
                metadata={'stage': 'account_verified'},
            )

            otp.delete()

            from referrals.services import finalize_referral_on_email_verified

            finalize_referral_on_email_verified(user)

            return Response({'message': 'Email validé avec succès'}, status=status.HTTP_200_OK)

        except (User.DoesNotExist, EmailOTP.DoesNotExist):
            return Response({'error': 'Code OTP invalide'}, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email requis'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            # Vérifier si l'email est déjà vérifié
            if EmailAddress.objects.filter(user=user, email=email, verified=True).exists():
                return Response({'error': 'Cet email est déjà vérifié'}, status=status.HTTP_400_BAD_REQUEST)
            
            otp, created = EmailOTP.objects.get_or_create(user=user, defaults={'expires_at': timezone.now() + timedelta(minutes=10)})
            otp.generate_otp()

            try:
                send_pinova_mail(
                    'Nouveau code de validation PINOVA',
                    f'Votre nouveau code de validation est : {otp.otp_code}. Il expire dans 10 minutes.',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except EmailDeliveryUnavailable:
                return Response(
                    {
                        'error': EMAIL_DELIVERY_USER_MESSAGE,
                        'code': EMAIL_DELIVERY_ERROR_CODE,
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response({'message': 'Nouveau code envoyé'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable'}, status=status.HTTP_404_NOT_FOUND)

class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    lookup_field = 'user__username'

    def get_queryset(self):
        qs = Profile.objects.select_related('user')
        if getattr(self, 'action', None) != 'list':
            return qs
        q = (self.request.query_params.get('q') or '').strip()
        if not q:
            return Profile.objects.none()
        qs = qs.filter(discoverable_profile=True).filter(
            models.Q(user__username__icontains=q) | models.Q(display_name__icontains=q)
        )
        viewer = self.request.user
        if viewer.is_authenticated:
            qs = qs.exclude(user_id=viewer.id)
            forb = blocked_mutual_user_ids(viewer)
            if forb:
                qs = qs.exclude(user_id__in=forb)
        return qs.order_by('user__username')

    def _share_access_ok(self, request, profile):
        if not profile.share_token:
            return False
        share_raw = (request.query_params.get('share') or '').strip()
        if not share_raw:
            return False
        try:
            return uuid.UUID(share_raw) == profile.share_token
        except ValueError:
            return False

    def retrieve(self, request, *args, **kwargs):
        profile = self.get_object()
        if request.user.is_authenticated and users_are_mutually_blocked(request.user, profile.user):
            return Response(
                {'error': 'This profile is unavailable.', 'code': 'user_blocked'},
                status=status.HTTP_403_FORBIDDEN,
            )
        share_ok = self._share_access_ok(request, profile)
        if profile.private_profile:
            is_owner = request.user.is_authenticated and request.user == profile.user
            is_follower = (
                request.user.is_authenticated
                and profile.followers.filter(user=request.user).exists()
            )
            if not is_owner and not is_follower and not share_ok:
                return Response({'error': 'This profile is private'}, status=status.HTTP_403_FORBIDDEN)
        serializer = UserSerializer(profile.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def follow(self, request, user__username=None):
        profile_to_follow = self.get_object()
        current_user_profile = request.user.profile
        
        if current_user_profile == profile_to_follow:
            return Response({'error': 'You cannot follow yourself'}, status=status.HTTP_400_BAD_REQUEST)

        if users_are_mutually_blocked(request.user, profile_to_follow.user):
            return Response({'error': 'Interaction not allowed'}, status=status.HTTP_400_BAD_REQUEST)

        if current_user_profile.following.filter(id=profile_to_follow.id).exists():
            current_user_profile.following.remove(profile_to_follow)
            return Response({'status': 'unfollowed'})
        else:
            current_user_profile.following.add(profile_to_follow)
            # Ici on pourrait créer une notification
            if profile_to_follow.notifications_followers:
                create_localized_notification(
                    recipient=profile_to_follow.user,
                    sender=request.user,
                    notification_type='follow',
                    message_fr=f"{request.user.username} a commencé à vous suivre.",
                    action_url=f'/profile/{request.user.username}',
                )
            return Response({'status': 'followed'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='report')
    def report_profile(self, request, user__username=None):
        from pins.models import ContentReport
        from pins.report_constants import REPORT_DETAILS_MAX_LEN, normalize_report_category

        profile = self.get_object()
        if profile.user_id == request.user.id:
            return Response({'error': 'Cannot report yourself'}, status=status.HTTP_400_BAD_REQUEST)
        if users_are_mutually_blocked(request.user, profile.user):
            return Response({'error': 'Interaction not allowed'}, status=status.HTTP_400_BAD_REQUEST)
        if ContentReport.objects.filter(reporter=request.user, reported_user=profile.user).exists():
            return Response({'error': 'already_reported'}, status=status.HTTP_409_CONFLICT)
        category = normalize_report_category(request.data.get('category'))
        details = str(request.data.get('details') or '').strip()[:REPORT_DETAILS_MAX_LEN]
        if not details:
            details = str(request.data.get('reason') or '').strip()[:REPORT_DETAILS_MAX_LEN]
        if len(details) < 10:
            return Response(
                {'details': ['Merci d’ajouter une brève description (10 caractères minimum).']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ContentReport.objects.create(
                reporter=request.user,
                reported_user=profile.user,
                category=category,
                details=details,
                reason=details[:500],
            )
        except IntegrityError:
            return Response({'error': 'already_reported'}, status=status.HTTP_409_CONFLICT)
        return Response({'status': 'ok'})

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], url_path='followers')
    def followers(self, request, user__username=None):
        profile = self.get_object()
        share_ok = self._share_access_ok(request, profile)
        if profile.private_profile:
            is_owner = request.user.is_authenticated and request.user == profile.user
            is_follower = (
                request.user.is_authenticated
                and profile.followers.filter(user=request.user).exists()
            )
            if not is_owner and not is_follower and not share_ok:
                return Response({'error': 'This profile is private'}, status=status.HTTP_403_FORBIDDEN)
        forb = blocked_mutual_user_ids(request.user) if request.user.is_authenticated else frozenset()
        data = []
        for follower in profile.followers.select_related('user').order_by('user__username')[:200]:
            if forb and follower.user_id in forb:
                continue
            data.append(
                {
                    'username': follower.user.username,
                    'display_name': follower.display_name or follower.user.username,
                    'avatar_color': follower.avatar_color or 'bg-neutral-400',
                    'avatar': build_versioned_media_url(request, follower.avatar)
                    if follower.avatar and getattr(follower.avatar, 'name', '')
                    else None,
                    'is_pro': follower.subscription_plan == Profile.PLAN_PRO,
                }
            )
        return Response({'results': data})

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], url_path='following')
    def following(self, request, user__username=None):
        profile = self.get_object()
        share_ok = self._share_access_ok(request, profile)
        if profile.private_profile:
            is_owner = request.user.is_authenticated and request.user == profile.user
            is_follower = (
                request.user.is_authenticated
                and profile.followers.filter(user=request.user).exists()
            )
            if not is_owner and not is_follower and not share_ok:
                return Response({'error': 'This profile is private'}, status=status.HTTP_403_FORBIDDEN)
        forb = blocked_mutual_user_ids(request.user) if request.user.is_authenticated else frozenset()
        data = []
        for followed in profile.following.select_related('user').order_by('user__username')[:200]:
            if forb and followed.user_id in forb:
                continue
            data.append(
                {
                    'username': followed.user.username,
                    'display_name': followed.display_name or followed.user.username,
                    'avatar_color': followed.avatar_color or 'bg-neutral-400',
                    'avatar': build_versioned_media_url(request, followed.avatar)
                    if followed.avatar and getattr(followed.avatar, 'name', '')
                    else None,
                    'is_pro': followed.subscription_plan == Profile.PLAN_PRO,
                }
            )
        return Response({'results': data})


class UserBlockViewSet(viewsets.ModelViewSet):
    """Liste / création / suppression des comptes bloqués par l’utilisateur connecté."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserBlockSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return (
            UserBlock.objects.filter(blocker=self.request.user)
            .select_related('blocked', 'blocked__profile')
            .order_by('-created_at')
        )

    def create(self, request, *args, **kwargs):
        raw = (request.data.get('username') or '').strip()
        if not raw:
            return Response({'username': ['Ce champ est requis.']}, status=status.HTTP_400_BAD_REQUEST)
        target = User.objects.filter(username__iexact=raw).first()
        if not target:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return Response({'error': 'Cannot block yourself'}, status=status.HTTP_400_BAD_REQUEST)
        obj, created = UserBlock.objects.get_or_create(blocker=request.user, blocked=target)
        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class QTextSearchFilter(filters.SearchFilter):
    """Paramètre `q` (mobile) ou `search` (DRF) pour filtrer username + display_name."""

    def get_search_terms(self, request):
        raw = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        if not raw:
            return []
        raw = raw.replace('\x00', '').replace(',', ' ')
        return raw.split()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [QTextSearchFilter]
    search_fields = ['username', 'profile__display_name']

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def mentions(self, request):
        query = (request.query_params.get('q') or '').strip()
        users = User.objects.select_related('profile').filter(profile__discoverable_profile=True)
        viewer = getattr(request, 'user', None)
        if viewer and viewer.is_authenticated:
            users = users.exclude(pk=viewer.pk)
            forb = blocked_mutual_user_ids(viewer)
            if forb:
                users = users.exclude(pk__in=forb)

        if query:
            users = users.filter(
                models.Q(username__icontains=query) |
                models.Q(profile__display_name__icontains=query)
            )

        class MentionPagination(PageNumberPagination):
            page_size = 10
            page_size_query_param = 'page_size'
            max_page_size = 30

        paginator = MentionPagination()

        if viewer and viewer.is_authenticated:
            my_profile = viewer.profile
            since = timezone.now() - timedelta(days=60)

            fu = frozenset(my_profile.following.values_list('user_id', flat=True))
            fru = frozenset(my_profile.followers.values_list('user_id', flat=True))
            mutual = fu & fru
            following_only = fu - mutual
            follower_only = fru - mutual

            rank_whens = []
            if mutual:
                rank_whens.append(models.When(models.Q(pk__in=list(mutual)), then=models.Value(0)))
            if following_only:
                rank_whens.append(models.When(models.Q(pk__in=list(following_only)), then=models.Value(1)))
            if follower_only:
                rank_whens.append(models.When(models.Q(pk__in=list(follower_only)), then=models.Value(2)))

            users = users.annotate(
                view_score=models.Count(
                    'pins__view_events',
                    filter=models.Q(
                        pins__view_events__user=viewer,
                        pins__view_events__created_at__gte=since,
                    ),
                ),
                rank_group=models.Case(
                    *rank_whens,
                    default=models.Value(3),
                    output_field=models.IntegerField(),
                ),
            ).order_by('rank_group', '-view_score', 'username')
            page = paginator.paginate_queryset(users, request)
            data = []
            for user in page:
                rel = ''
                if mutual and user.pk in mutual:
                    rel = 'mutual'
                elif following_only and user.pk in following_only:
                    rel = 'following'
                elif follower_only and user.pk in follower_only:
                    rel = 'follower'
                elif getattr(user, 'view_score', 0) > 0:
                    rel = 'often_viewed'
                data.append(
                    {
                        'username': user.username,
                        'display_name': user.profile.display_name or user.username,
                        'avatar_color': user.profile.avatar_color or 'bg-neutral-400',
                        'avatar': build_versioned_media_url(request, user.profile.avatar)
                        if user.profile.avatar and getattr(user.profile.avatar, 'name', '')
                        else None,
                        'relation': rel,
                    }
                )
            return paginator.get_paginated_response(data)

        users = users.order_by('username')
        page = paginator.paginate_queryset(users, request)
        data = [
            {
                'username': user.username,
                'display_name': user.profile.display_name or user.username,
                'avatar_color': user.profile.avatar_color or 'bg-neutral-400',
                'avatar': build_versioned_media_url(request, user.profile.avatar)
                if user.profile.avatar and getattr(user.profile.avatar, 'name', '')
                else None,
                'relation': '',
            }
            for user in page
        ]
        return paginator.get_paginated_response(data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='follow-suggestions')
    def follow_suggestions(self, request):
        my_profile = request.user.profile
        following_ids = list(my_profile.following.values_list('user_id', flat=True))
        following_ids.append(request.user.id)
        exclude_user_ids = set(following_ids) | set(blocked_mutual_user_ids(request.user))

        raw_interests = (request.query_params.get('interests') or '').strip()
        onboarding_interests = []
        if raw_interests:
            if raw_interests.startswith('['):
                try:
                    parsed = json.loads(raw_interests)
                    if isinstance(parsed, list):
                        onboarding_interests = [str(x).strip() for x in parsed if str(x).strip()]
                except json.JSONDecodeError:
                    onboarding_interests = []
            else:
                onboarding_interests = [p.strip() for p in raw_interests.split(',') if p.strip()]

        onboarding_interests = interest_slugs_for_user(
            request.user,
            onboarding_interests or None,
        )

        country_param = (request.query_params.get('country_code') or '').strip().upper()[:2]

        candidates = (
            User.objects.select_related('profile')
            .exclude(id__in=exclude_user_ids)
            .filter(profile__discoverable_profile=True)
        )

        if onboarding_interests:
            annotate_kwargs = {
                'followers_total': models.Count('profile__followers', distinct=True),
            }
            order_fields: list[str] = []
            interest_candidates = candidates.annotate(**annotate_kwargs)
            if country_param:
                interest_candidates = interest_candidates.annotate(
                    country_boost=models.Case(
                        models.When(profile__country_code=country_param, then=models.Value(1)),
                        default=models.Value(0),
                        output_field=models.IntegerField(),
                    ),
                )
                order_fields.append('-country_boost')
            interest_candidates = interest_candidates.order_by(*order_fields, '-followers_total', 'username')
            matched_users = _users_with_shared_interests(
                interest_candidates,
                onboarding_interests,
                limit=24,
            )
            data = []
            for user in matched_users:
                reason = 'shared_interests'
                if country_param and getattr(user.profile, 'country_code', '') == country_param:
                    reason = 'near_you'
                data.append(
                    {
                        'username': user.username,
                        'display_name': user.profile.display_name or user.username,
                        'avatar_color': user.profile.avatar_color or 'bg-neutral-400',
                        'avatar': build_versioned_media_url(request, user.profile.avatar)
                        if user.profile.avatar and getattr(user.profile.avatar, 'name', '')
                        else None,
                        'is_pro': user.profile.subscription_plan == Profile.PLAN_PRO,
                        'reason': reason,
                    }
                )
            if not data:
                onboarding_interests = []
            else:
                return Response({'results': data})

        topic_rows = (
            request.user.likes.select_related('pin')
            .exclude(pin__topic__isnull=True)
            .values('pin__topic__name')
            .annotate(score=models.Count('id'))
            .order_by('-score')[:8]
        )
        preferred_topics = [row['pin__topic__name'] for row in topic_rows]

        candidates = (
            User.objects.select_related('profile')
            .exclude(id__in=exclude_user_ids)
            .filter(profile__discoverable_profile=True)
            .annotate(
                followers_total=models.Count('profile__followers', distinct=True),
                preferred_topic_pins=models.Count(
                    'pins',
                    filter=models.Q(pins__topic__name__in=preferred_topics),
                    distinct=True,
                ),
            )
            .order_by('-preferred_topic_pins', '-followers_total', 'username')[:30]
        )

        data = [
            {
                'username': user.username,
                'display_name': user.profile.display_name or user.username,
                'avatar_color': user.profile.avatar_color or 'bg-neutral-400',
                'avatar': build_versioned_media_url(request, user.profile.avatar)
                if user.profile.avatar and getattr(user.profile.avatar, 'name', '')
                else None,
                'is_pro': user.profile.subscription_plan == Profile.PLAN_PRO,
                'reason': 'preferred_topic' if user.preferred_topic_pins > 0 else 'popular',
            }
            for user in candidates
        ]
        return Response({'results': data})

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _resolve_user_currency(request)
        from pins.scheduled_publish_utils import publish_user_due_scheduled_pins

        publish_user_due_scheduled_pins(request.user, limit=50)
        from pins.me_hydration import build_me_hydration_bundle

        data = UserSerializer(
            request.user, context={'request': request, 'omit_full_board_list': True},
        ).data
        data.update(build_me_hydration_bundle(request))
        data['has_usable_password'] = request.user.has_usable_password()
        from referrals.services import build_me_referral_payload

        data['referral'] = build_me_referral_payload(request.user, request)
        return Response(data)

    def patch(self, request):
        user = request.user
        profile = user.profile
        _enforce_subscription_state(profile)

        # Update user fields
        if 'email' in request.data:
            user.email = request.data['email']
            user.save()

        if 'username' in request.data:
            new_username = re.sub(r'[^\w.@+-]', '', str(request.data.get('username') or '').strip(), flags=re.UNICODE)
            if new_username and new_username != user.username:
                if User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
                    return Response({'username': ['Ce nom d’utilisateur est déjà pris.']}, status=status.HTTP_400_BAD_REQUEST)
                user.username = new_username
                user.save()

        mutable_data, bad_json_key = _patch_payload_from_request(request)
        if mutable_data is None:
            return Response({bad_json_key: ['Invalid JSON']}, status=status.HTTP_400_BAD_REQUEST)

        if str(mutable_data.get('complete_onboarding', '')).lower() in ('true', '1', 'yes'):
            profile.onboarding_completed_at = timezone.now()
            profile.save(update_fields=['onboarding_completed_at'])
            mutable_data.pop('complete_onboarding', None)

        # Tips & monetization are reserved for Pro.
        if profile.subscription_plan != Profile.PLAN_PRO:
            mutable_data['tips_enabled'] = False
            mutable_data['tips_url'] = ''

        if 'private_profile' in mutable_data:
            mutable_data['private_profile'] = str(mutable_data.get('private_profile')).lower() == 'true'
        if 'notifications_followers' in mutable_data:
            mutable_data['notifications_followers'] = str(mutable_data.get('notifications_followers')).lower() == 'true'
        if 'notifications_saves' in mutable_data:
            mutable_data['notifications_saves'] = str(mutable_data.get('notifications_saves')).lower() == 'true'
        if 'notifications_recommendations' in mutable_data:
            mutable_data['notifications_recommendations'] = str(mutable_data.get('notifications_recommendations')).lower() == 'true'
        if profile.subscription_plan != Profile.PLAN_PRO:
            mutable_data.pop('notifications_digest_creator_weekly', None)
        elif 'notifications_digest_creator_weekly' in mutable_data:
            mutable_data['notifications_digest_creator_weekly'] = str(
                mutable_data.get('notifications_digest_creator_weekly'),
            ).lower() == 'true'

        if profile.subscription_plan not in {Profile.PLAN_PLUS, Profile.PLAN_PRO}:
            mutable_data.pop('sensitive_media_blur_by_default', None)
        elif 'sensitive_media_blur_by_default' in mutable_data:
            mutable_data['sensitive_media_blur_by_default'] = (
                str(mutable_data.get('sensitive_media_blur_by_default')).lower() == 'true'
            )

        if profile.subscription_plan == Profile.PLAN_FREE:
            mutable_data.pop('ad_ads_enabled', None)
            mutable_data.pop('partner_ads_enabled', None)
        elif profile.subscription_plan == Profile.PLAN_PLUS:
            mutable_data.pop('partner_ads_enabled', None)
            if 'ad_ads_enabled' in mutable_data:
                mutable_data['ad_ads_enabled'] = str(mutable_data.get('ad_ads_enabled')).lower() in (
                    'true',
                    '1',
                    'yes',
                )
        else:
            for ad_key in ('ad_ads_enabled', 'partner_ads_enabled'):
                if ad_key in mutable_data:
                    mutable_data[ad_key] = str(mutable_data.get(ad_key)).lower() in ('true', '1', 'yes')

        if 'hide_sensitive_pins' in mutable_data:
            from pins.visibility import profile_is_verified_adult as _profile_verified_adult

            if _profile_verified_adult(profile):
                mutable_data['hide_sensitive_pins'] = (
                    str(mutable_data.get('hide_sensitive_pins')).lower() == 'true'
                )
            else:
                mutable_data.pop('hide_sensitive_pins', None)

        # Search visibility maps to discoverable_profile.
        if 'discoverable_profile' in mutable_data:
            mutable_data['discoverable_profile'] = str(mutable_data.get('discoverable_profile')).lower() == 'true'

        for bool_key in (
            'show_activity', 'show_last_seen', 'allow_dm', 'allow_tags_mentions',
            'allow_ai_translation',
        ):
            if bool_key in mutable_data:
                mutable_data[bool_key] = str(mutable_data.get(bool_key)).lower() in ('true', '1', 'yes')

        preferred_currency = mutable_data.get('preferred_currency')
        if preferred_currency is not None:
            normalized_currency = normalize_currency(preferred_currency)
            if not normalized_currency:
                return Response({'preferred_currency': ['Unsupported currency code']}, status=status.HTTP_400_BAD_REQUEST)
            mutable_data['preferred_currency'] = normalized_currency

        # Update profile fields
        profile_serializer = ProfileSerializer(profile, data=mutable_data, partial=True)
        if profile_serializer.is_valid():
            profile_serializer.save()
            _resolve_user_currency(request)
            from pins.me_hydration import build_me_hydration_bundle

            payload = UserSerializer(
                user, context={'request': request, 'omit_full_board_list': True},
            ).data
            payload.update(build_me_hydration_bundle(request))
            payload['has_usable_password'] = request.user.has_usable_password()
            from referrals.services import build_me_referral_payload, try_apply_onboarding_referral

            if 'referral_code' in request.data:
                device_hdr = (request.META.get('HTTP_X_PINOVA_DEVICE_BINDING') or '').strip() or None
                payload['referral_onboarding'] = try_apply_onboarding_referral(
                    user,
                    referral_code_optional=str(request.data.get('referral_code') or ''),
                    request=request,
                    device_binding_header=device_hdr,
                )
            from referrals.models import ReferralAttribution
            from referrals.services import try_complete_referral_rewards

            _rattr = ReferralAttribution.objects.filter(referee=user).first()
            if _rattr:
                try_complete_referral_rewards(_rattr)
            payload['referral'] = build_me_referral_payload(request.user, request)
            return Response(payload)
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetInitialPasswordView(APIView):
    """Définit un mot de passe pour les comptes sans mot de passe utilisable (ex. Google uniquement)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.has_usable_password():
            return Response(
                {
                    'detail': 'Un mot de passe est déjà défini. Utilisez la modification de mot de passe.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = SetInitialPasswordSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data['new_password1'])
        request.user.save(update_fields=['password'])
        return Response({'ok': True, 'has_usable_password': True})


class ProfileShareTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Crée ou régénère le jeton ?share= pour un profil privé."""
        profile = request.user.profile
        regenerate = str(request.data.get('regenerate', '')).lower() in ('true', '1', 'yes')
        if regenerate or profile.share_token is None:
            profile.share_token = uuid.uuid4()
            profile.save(update_fields=['share_token'])
        return Response({'share_token': str(profile.share_token)})


class AccountDeletionRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Programme une suppression définitive du compte (purge serveur après 30 jours)."""
        raw = str(request.data.get('confirm', '')).strip().upper()
        if raw not in ('DELETE', 'SUPPRIMER'):
            return Response(
                {'confirm': ['La confirmation doit être DELETE ou SUPPRIMER.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = request.user.profile
        profile.account_scheduled_deletion_at = timezone.now() + timedelta(days=30)
        profile.save(update_fields=['account_scheduled_deletion_at'])
        return Response({'scheduled_at': profile.account_scheduled_deletion_at.isoformat()})


class AccountDeletionCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile = request.user.profile
        profile.account_scheduled_deletion_at = None
        profile.save(update_fields=['account_scheduled_deletion_at'])
        return Response({'ok': True})


class SubscriptionCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _fedapay_base_url(self):
        env = os.environ.get('FEDAPAY_ENV', 'sandbox').strip().lower()
        if env == 'live':
            return 'https://api.fedapay.com/v1'
        return 'https://sandbox-api.fedapay.com/v1'

    def _fedapay_headers(self):
        secret_key = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
        if not secret_key:
            return None
        return {
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        }

    def _should_expose_debug(self):
        return settings.DEBUG or os.environ.get('FEDAPAY_VERBOSE_ERRORS', 'False').lower() == 'true'

    def _safe_json(self, response):
        try:
            return response.json()
        except ValueError:
            return None

    def _extract_transaction_id(self, payload):
        if not isinstance(payload, dict):
            return None
        direct = payload.get('id')
        if direct:
            return direct
        for key in ('transaction', 'data', 'v1/transaction'):
            nested = payload.get(key)
            if isinstance(nested, dict) and nested.get('id'):
                return nested.get('id')
        return None

    def _extract_checkout_url(self, payload):
        if not isinstance(payload, dict):
            return None
        for key in ('url', 'payment_url', 'redirect_url'):
            if payload.get(key):
                return payload.get(key)
        for key in ('token', 'data'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                for nested_key in ('url', 'payment_url', 'redirect_url'):
                    if nested.get(nested_key):
                        return nested.get(nested_key)
        return None

    def post(self, request):
        plan = (request.data.get('plan') or '').strip().lower()
        billing_cycle = (request.data.get('billing_cycle') or 'monthly').strip().lower()
        if plan not in {Profile.PLAN_PLUS, Profile.PLAN_PRO}:
            return Response({'error': 'Invalid plan'}, status=status.HTTP_400_BAD_REQUEST)
        if billing_cycle not in {'monthly', 'yearly'}:
            return Response({'error': 'Invalid billing cycle'}, status=status.HTTP_400_BAD_REQUEST)

        payer = request.user.profile
        _enforce_subscription_state(payer)
        payer.refresh_from_db()
        if payer.subscription_sponsor_id:
            return Response(
                {
                    'error': (
                        'Vous êtes sur un abonnement partagé. Quittez le groupe (Paramètres) '
                        'avant de souscrire un abonnement personnel.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        headers = self._fedapay_headers()
        if not headers:
            return Response({'error': 'FedaPay is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        seat_bundle = _normalized_seat_bundle(request.data.get('seat_bundle'))
        catalog = _catalog_entry(plan, billing_cycle, seat_bundle)
        if not catalog:
            return Response({'error': 'Unsupported pricing configuration'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        base_amount = int(catalog['amount'])
        duration_days = int(catalog['duration_days'])
        base_currency_iso = (catalog.get('currency_iso') or os.environ.get('FEDAPAY_CURRENCY_ISO', 'XOF')).upper()
        target_currency, detected_country = _resolve_user_currency(request)
        converted_amount = convert_minor_amount(base_amount, base_currency_iso, target_currency)
        if converted_amount is None:
            amount = base_amount
            currency_iso = base_currency_iso
            conversion_applied = False
        else:
            amount = converted_amount
            currency_iso = target_currency
            conversion_applied = True

        default_callback_url = f"{str(settings.FRONTEND_URL).rstrip('/')}/premium"
        callback_url = _normalize_url_path_slashes(
            os.environ.get('FEDAPAY_CALLBACK_URL') or default_callback_url
        )
        first_name, last_name = _fedapay_checkout_customer_names(request.user)

        payload = {
            'description': _fedapay_checkout_description(plan, billing_cycle, seat_bundle),
            'amount': amount,
            'currency': {'iso': currency_iso},
            'callback_url': callback_url,
            'customer': {
                'email': request.user.email,
                'firstname': first_name[:100],
                'lastname': last_name[:100],
            },
        }

        base = self._fedapay_base_url()
        try:
            create_resp = requests.post(f'{base}/transactions', json=payload, headers=headers, timeout=20)
            create_body = self._safe_json(create_resp)
            if create_resp.status_code >= 400:
                logger.error('FedaPay transaction create failed status=%s body=%s', create_resp.status_code, create_resp.text)
                error_payload = {'error': 'FedaPay transaction create failed'}
                if self._should_expose_debug():
                    error_payload['fedapay_debug'] = {
                        'step': 'create_transaction',
                        'status_code': create_resp.status_code,
                        'response_body': create_body if create_body is not None else create_resp.text,
                    }
                return Response(error_payload, status=status.HTTP_502_BAD_GATEWAY)

            transaction_data = create_body or {}
            transaction_id = self._extract_transaction_id(transaction_data)
            if not transaction_id:
                logger.error('FedaPay transaction response missing id body=%s', create_resp.text)
                error_payload = {'error': 'Invalid FedaPay transaction response'}
                if self._should_expose_debug():
                    error_payload['fedapay_debug'] = {
                        'step': 'create_transaction',
                        'status_code': create_resp.status_code,
                        'response_body': transaction_data if transaction_data else create_resp.text,
                        'hint': 'Missing transaction id in response payload',
                    }
                return Response(error_payload, status=status.HTTP_502_BAD_GATEWAY)

            token_resp = requests.post(f'{base}/transactions/{transaction_id}/token', headers=headers, timeout=20)
            token_body = self._safe_json(token_resp)
            if token_resp.status_code >= 400:
                logger.error('FedaPay token create failed tx=%s status=%s body=%s', transaction_id, token_resp.status_code, token_resp.text)
                error_payload = {'error': 'Unable to generate checkout URL'}
                if self._should_expose_debug():
                    error_payload['fedapay_debug'] = {
                        'step': 'create_transaction_token',
                        'status_code': token_resp.status_code,
                        'response_body': token_body if token_body is not None else token_resp.text,
                        'transaction_id': str(transaction_id),
                    }
                return Response(error_payload, status=status.HTTP_502_BAD_GATEWAY)

            token_data = token_body or {}
            checkout_url = self._extract_checkout_url(token_data)
            if not checkout_url:
                logger.error('FedaPay token response missing checkout url tx=%s body=%s', transaction_id, token_resp.text)
                error_payload = {'error': 'Unable to generate checkout URL'}
                if self._should_expose_debug():
                    error_payload['fedapay_debug'] = {
                        'step': 'create_transaction_token',
                        'status_code': token_resp.status_code,
                        'response_body': token_data if token_data else token_resp.text,
                        'transaction_id': str(transaction_id),
                        'hint': 'Missing checkout url in token response payload',
                    }
                return Response(error_payload, status=status.HTTP_502_BAD_GATEWAY)

            SubscriptionPayment.objects.update_or_create(
                fedapay_transaction_id=str(transaction_id),
                defaults={
                    'user': request.user,
                    'plan': plan,
                    'billing_cycle': billing_cycle,
                    'amount': amount,
                    'currency_iso': currency_iso,
                    'fedapay_reference': str(transaction_data.get('reference') or ''),
                    'status': SubscriptionPayment.STATUS_PENDING,
                    'checkout_url': checkout_url,
                    'promo_bundle': seat_bundle,
                    'fedapay_payload': {
                        'transaction': transaction_data,
                        'token': token_data,
                    },
                },
            )

            return Response({
                'checkout_url': checkout_url,
                'transaction_id': str(transaction_id),
                'pricing': {
                    'plan': plan,
                    'billing_cycle': billing_cycle,
                    'amount_minor': amount,
                    'amount_display': _display_amount(amount, currency_iso),
                    'currency_iso': currency_iso,
                    'duration_days': duration_days,
                    'base_amount_minor': base_amount,
                    'base_currency_iso': base_currency_iso,
                    'conversion_applied': conversion_applied,
                    'seat_bundle': seat_bundle,
                    'bundle_discount_fraction': 0.0,
                },
            }, status=status.HTTP_201_CREATED)
        except requests.RequestException as exc:
            logger.exception('FedaPay checkout request exception')
            error_payload = {'error': f'FedaPay error: {str(exc)}'}
            if self._should_expose_debug():
                response_obj = getattr(exc, 'response', None)
                error_payload['fedapay_debug'] = {
                    'step': 'network_or_http_exception',
                    'status_code': getattr(response_obj, 'status_code', None),
                    'response_body': self._safe_json(response_obj) if response_obj is not None else None,
                }
            return Response(error_payload, status=status.HTTP_502_BAD_GATEWAY)


class SubscriptionConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _fedapay_base_url(self):
        env = os.environ.get('FEDAPAY_ENV', 'sandbox').strip().lower()
        if env == 'live':
            return 'https://api.fedapay.com/v1'
        return 'https://sandbox-api.fedapay.com/v1'

    def _fedapay_headers(self):
        secret_key = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
        if not secret_key:
            return None
        return {
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        }

    def _extract_amount(self, tx_payload):
        if not isinstance(tx_payload, dict):
            return None
        direct = tx_payload.get('amount')
        if isinstance(direct, (int, float)):
            return int(direct)
        for key in ('transaction', 'data', 'v1/transaction'):
            nested = tx_payload.get(key)
            if isinstance(nested, dict):
                value = nested.get('amount')
                if isinstance(value, (int, float)):
                    return int(value)
        return None

    def _apply_subscription(self, profile, payment, duration_days):
        from .subscription_seats import refresh_seat_hub_after_owner_change

        prev_bundle = (profile.subscription_seat_bundle or SUBSCRIPTION_BUNDLE_SOLO).strip().lower()
        profile.subscription_plan = payment.plan
        profile.subscription_cancel_at_period_end = False
        profile.subscription_scheduled_plan = ''
        base_start = timezone.now()
        if profile.subscription_renewal_at and profile.subscription_renewal_at > base_start:
            base_start = profile.subscription_renewal_at
        profile.subscription_renewal_at = base_start + timedelta(days=duration_days)
        if payment.plan == Profile.PLAN_FREE:
            profile.translation_quota_monthly = 5
            profile.subscription_seat_bundle = SUBSCRIPTION_BUNDLE_SOLO
        else:
            profile.translation_quota_monthly = 100000
            profile.subscription_seat_bundle = _normalized_seat_bundle(payment.promo_bundle)
        profile.translation_used_monthly = 0
        profile.save()
        profile.refresh_from_db()
        refresh_seat_hub_after_owner_change(profile, prev_bundle)

    def _notify_payment_events(self, user, payment, previous_plan):
        create_localized_notification(
            recipient=user,
            sender=None,
            notification_type='payment',
            title_fr='Paiement confirmé',
            message_fr=(
                f"Paiement confirmé ({payment.billing_cycle}) : "
                f"{payment.amount} {payment.currency_iso} pour le plan {payment.plan.upper()}."
            ),
            action_url='/premium',
            metadata={
                'transaction_id': payment.fedapay_transaction_id,
                'plan': payment.plan,
                'billing_cycle': payment.billing_cycle,
            },
        )
        if previous_plan != payment.plan:
            create_localized_notification(
                recipient=user,
                sender=None,
                notification_type='plan_change',
                title_fr='Changement de plan',
                message_fr=f"Votre plan est passé de {previous_plan.upper()} à {payment.plan.upper()}.",
                action_url='/premium',
                metadata={
                    'from_plan': previous_plan,
                    'to_plan': payment.plan,
                    'transaction_id': payment.fedapay_transaction_id,
                },
            )

    def post(self, request):
        transaction_id = str(request.data.get('transaction_id') or '').strip()
        callback_status = str(request.data.get('callback_status') or '').strip().lower()
        if not transaction_id:
            return Response({'error': 'transaction_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = SubscriptionPayment.objects.get(
                fedapay_transaction_id=transaction_id,
                user=request.user,
            )
        except SubscriptionPayment.DoesNotExist:
            return Response({'error': 'Payment session not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == SubscriptionPayment.STATUS_APPROVED:
            logger.info(
                'fedapay_confirm: déjà approuvé — user_id=%s transaction_id=%s payment_id=%s',
                request.user.pk,
                transaction_id,
                payment.id,
            )
            return Response({
                'status': 'approved',
                'plan': payment.plan,
                'billing_cycle': payment.billing_cycle,
                'renewal_at': request.user.profile.subscription_renewal_at,
                'already_confirmed': True,
            })

        headers = self._fedapay_headers()
        if not headers:
            return Response({'error': 'FedaPay is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        seat_bundle_pay = _normalized_seat_bundle(payment.promo_bundle)
        catalog = _catalog_entry(payment.plan, payment.billing_cycle, seat_bundle_pay)
        duration_days = int((catalog or {}).get('duration_days') or 30)
        expected_amount = int(payment.amount)

        base = self._fedapay_base_url()
        logger.info(
            'fedapay_confirm: début — user_id=%s transaction_id=%s payment_id=%s plan=%s cycle=%s '
            'callback_status=%s expected_amount=%s api_base=%s',
            request.user.pk,
            transaction_id,
            payment.id,
            payment.plan,
            payment.billing_cycle,
            callback_status or '(vide)',
            expected_amount,
            base,
        )
        approved_statuses = {'approved', 'success', 'successful', 'completed'}
        negative_statuses = {'canceled', 'cancelled', 'failed', 'declined', 'rejected'}
        transitional_statuses = {'', 'pending', 'processing', 'initialized', 'sent'}
        try:
            tx = {}
            for attempt in range(4):
                url = f'{base}/transactions/{transaction_id}'
                try:
                    logger.debug(
                        'fedapay_confirm: GET tentative=%s url=%s transaction_id=%s user_id=%s',
                        attempt + 1,
                        url,
                        transaction_id,
                        request.user.pk,
                    )
                    resp = requests.get(url, headers=headers, timeout=20)
                    resp.raise_for_status()
                    tx = resp.json() or {}
                except requests.RequestException as exc:
                    resp_obj = getattr(exc, 'response', None)
                    status_code = getattr(resp_obj, 'status_code', None)
                    body_preview = ''
                    if resp_obj is not None:
                        try:
                            body_preview = (resp_obj.text or '')[:2000]
                        except Exception:
                            body_preview = '(lecture corps impossible)'
                    logger.warning(
                        'fedapay_confirm: GET échoué — tentative=%s/%s user_id=%s transaction_id=%s '
                        'http_status=%s error=%s body_preview=%s',
                        attempt + 1,
                        4,
                        request.user.pk,
                        transaction_id,
                        status_code,
                        exc,
                        body_preview,
                    )
                    if attempt < 3:
                        time.sleep(0.45)
                        continue
                    raise
                if callback_status:
                    tx['callback_status'] = callback_status
                normalized_try = _fedapay_normalize_transaction_body(tx)
                status_try = _fedapay_normalized_status(normalized_try)
                logger.info(
                    'fedapay_confirm: GET OK — tentative=%s user_id=%s transaction_id=%s '
                    'http_status=%s statut_gateway=%s résumé=%s',
                    attempt + 1,
                    request.user.pk,
                    transaction_id,
                    resp.status_code,
                    status_try or '(vide)',
                    _fedapay_confirm_response_summary(tx, normalized_try),
                )
                if status_try in approved_statuses or status_try in negative_statuses:
                    break
                if attempt < 3 and status_try in transitional_statuses:
                    logger.info(
                        'fedapay_confirm: statut transitoire, nouvelle tentative — '
                        'tentative=%s statut=%s transaction_id=%s',
                        attempt + 1,
                        status_try or '(vide)',
                        transaction_id,
                    )
                    time.sleep(0.45)
                    continue
                break
            normalized = _fedapay_normalize_transaction_body(tx)
            paid_amount = self._extract_amount(normalized) or self._extract_amount(tx)
            if paid_amount is not None and paid_amount != expected_amount:
                logger.warning(
                    'fedapay_confirm: montant incohérent — user_id=%s transaction_id=%s '
                    'attendu=%s reçu=%s payment_id=%s',
                    request.user.pk,
                    transaction_id,
                    expected_amount,
                    paid_amount,
                    payment.id,
                )
                payment.status = SubscriptionPayment.STATUS_FAILED
                payment.fedapay_payload = {'transaction': tx, 'normalized': normalized, 'error': 'amount_mismatch'}
                payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
                return Response({
                    'status': 'failed',
                    'error': 'Payment amount mismatch',
                    'expected_amount': expected_amount,
                    'received_amount': paid_amount,
                }, status=status.HTTP_400_BAD_REQUEST)
            status_value = _fedapay_normalized_status(normalized)
            raw_status = status_value
            effective_status = status_value
            if (
                effective_status not in approved_statuses
                and callback_status in approved_statuses
                and effective_status not in negative_statuses
            ):
                logger.info(
                    'fedapay_confirm: fusion callback — user_id=%s transaction_id=%s '
                    'statut_gateway=%s callback=%s -> effective=%s',
                    request.user.pk,
                    transaction_id,
                    raw_status or '(vide)',
                    callback_status,
                    callback_status,
                )
                effective_status = callback_status

            if effective_status in approved_statuses:
                previous_plan = request.user.profile.subscription_plan
                payment.status = SubscriptionPayment.STATUS_APPROVED
                invoice_url = _extract_invoice_url_from_fedapay(normalized)
                uf = ['status', 'fedapay_payload', 'updated_at']
                if invoice_url:
                    payment.invoice_url = invoice_url
                    uf.append('invoice_url')
                with transaction.atomic():
                    payment.fedapay_payload = {
                        'transaction': tx,
                        'normalized': normalized,
                        'gateway_status': raw_status,
                        'callback_status': callback_status,
                        'effective_status': effective_status,
                    }
                    payment.save(update_fields=uf)
                    self._apply_subscription(request.user.profile, payment, duration_days)
                    self._notify_payment_events(request.user, payment, previous_plan)
                logger.info(
                    'fedapay_confirm: succès — user_id=%s transaction_id=%s payment_id=%s '
                    'statut_gateway=%s statut_effectif=%s montant_paye=%s attendu=%s résumé=%s',
                    request.user.pk,
                    transaction_id,
                    payment.id,
                    raw_status,
                    effective_status,
                    paid_amount,
                    expected_amount,
                    _fedapay_confirm_response_summary(tx, normalized),
                )
                return Response({
                    'status': 'approved',
                    'plan': payment.plan,
                    'billing_cycle': payment.billing_cycle,
                    'duration_days': duration_days,
                    'renewal_at': request.user.profile.subscription_renewal_at,
                    'gateway_status': raw_status,
                    'callback_status': callback_status,
                    'effective_status': effective_status,
                })
            if effective_status in {'canceled', 'cancelled'}:
                payment.status = SubscriptionPayment.STATUS_CANCELED
            elif effective_status in {'failed', 'declined', 'rejected'}:
                payment.status = SubscriptionPayment.STATUS_FAILED
            else:
                payment.status = SubscriptionPayment.STATUS_PENDING
            payment.fedapay_payload = {
                'transaction': tx,
                'normalized': normalized,
                'gateway_status': raw_status,
                'callback_status': callback_status,
                'effective_status': effective_status,
            }
            payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
            logger.info(
                'fedapay_confirm: terminé sans approbation — user_id=%s transaction_id=%s payment_id=%s '
                'statut_paiement=%s statut_gateway=%s statut_effectif=%s callback=%s résumé=%s',
                request.user.pk,
                transaction_id,
                payment.id,
                payment.status,
                raw_status,
                effective_status,
                callback_status or '(vide)',
                _fedapay_confirm_response_summary(tx, normalized),
            )
            return Response({
                'status': payment.status,
                'gateway_status': raw_status,
                'callback_status': callback_status,
                'effective_status': effective_status,
            })
        except requests.RequestException as exc:
            resp_obj = getattr(exc, 'response', None)
            status_code = getattr(resp_obj, 'status_code', None)
            body_preview = ''
            if resp_obj is not None:
                try:
                    body_preview = (resp_obj.text or '')[:2000]
                except Exception:
                    body_preview = '(lecture corps impossible)'
            logger.error(
                'fedapay_confirm: échec définitif après tentatives — user_id=%s transaction_id=%s '
                'http_status=%s error=%s body_preview=%s',
                request.user.pk,
                transaction_id,
                status_code,
                exc,
                body_preview,
                exc_info=True,
            )
            return Response({'error': f'FedaPay error: {str(exc)}'}, status=status.HTTP_502_BAD_GATEWAY)


class SubscriptionManageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        _enforce_subscription_state(profile)
        return Response({
            'plan': profile.subscription_plan,
            'renewal_at': profile.subscription_renewal_at,
            'cancel_at_period_end': profile.subscription_cancel_at_period_end,
            'scheduled_plan': profile.subscription_scheduled_plan or None,
        })

    def post(self, request):
        action = str(request.data.get('action') or '').strip().lower()
        profile = request.user.profile
        _enforce_subscription_state(profile)
        if action == 'cancel':
            if profile.subscription_plan == Profile.PLAN_FREE:
                return Response({'error': 'No paid plan to cancel'}, status=status.HTTP_400_BAD_REQUEST)
            profile.subscription_cancel_at_period_end = True
            profile.subscription_scheduled_plan = Profile.PLAN_FREE
            profile.save(update_fields=['subscription_cancel_at_period_end', 'subscription_scheduled_plan'])
            return Response({'status': 'scheduled_cancel', 'scheduled_plan': Profile.PLAN_FREE})
        if action == 'reactivate':
            profile.subscription_cancel_at_period_end = False
            profile.subscription_scheduled_plan = ''
            profile.save(update_fields=['subscription_cancel_at_period_end', 'subscription_scheduled_plan'])
            return Response({'status': 'reactivated'})
        if action == 'downgrade_to_free':
            profile.subscription_cancel_at_period_end = True
            profile.subscription_scheduled_plan = Profile.PLAN_FREE
            profile.save(update_fields=['subscription_cancel_at_period_end', 'subscription_scheduled_plan'])
            return Response({'status': 'scheduled_downgrade', 'scheduled_plan': Profile.PLAN_FREE})
        if action == 'schedule_plan_change':
            target = str(request.data.get('target_plan') or '').strip().lower()
            if profile.subscription_plan == Profile.PLAN_FREE:
                return Response({'error': 'No active paid subscription'}, status=status.HTTP_400_BAD_REQUEST)
            if target not in {Profile.PLAN_PLUS, Profile.PLAN_FREE}:
                return Response({'error': 'Invalid target_plan'}, status=status.HTTP_400_BAD_REQUEST)
            if target == Profile.PLAN_PLUS and profile.subscription_plan != Profile.PLAN_PRO:
                return Response({'error': 'Only Pro accounts can schedule a switch to Plus'}, status=status.HTTP_400_BAD_REQUEST)
            if target == Profile.PLAN_PLUS:
                profile.subscription_scheduled_plan = Profile.PLAN_PLUS
                profile.subscription_cancel_at_period_end = False
            else:
                profile.subscription_scheduled_plan = Profile.PLAN_FREE
                profile.subscription_cancel_at_period_end = True
            profile.save(update_fields=['subscription_cancel_at_period_end', 'subscription_scheduled_plan'])
            return Response({
                'status': 'scheduled_plan_change',
                'scheduled_plan': profile.subscription_scheduled_plan,
                'cancel_at_period_end': profile.subscription_cancel_at_period_end,
            })
        if action == 'cancel_schedule':
            profile.subscription_scheduled_plan = ''
            profile.subscription_cancel_at_period_end = False
            profile.save(update_fields=['subscription_scheduled_plan', 'subscription_cancel_at_period_end'])
            return Response({'status': 'schedule_cleared'})
        return Response({'error': 'Unsupported action'}, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        expected_secret = (os.environ.get('FEDAPAY_WEBHOOK_SECRET') or '').strip()
        provided_secret = str(
            request.headers.get('X-Webhook-Token')
            or request.headers.get('X-Fedapay-Webhook-Token')
            or request.data.get('webhook_token')
            or ''
        ).strip()
        if expected_secret and provided_secret != expected_secret:
            return Response({'error': 'Invalid webhook token'}, status=status.HTTP_403_FORBIDDEN)

        tx_id = _fedapay_webhook_transaction_id(dict(request.data))
        if not tx_id:
            return Response({'error': 'transaction_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        status_value = _fedapay_webhook_status(dict(request.data))
        approved_statuses = {'approved', 'success', 'successful', 'completed'}
        payment = SubscriptionPayment.objects.filter(fedapay_transaction_id=tx_id).select_related('user', 'user__profile').first()
        if not payment:
            if status_value in approved_statuses:
                from monetization.views import approve_boost_payment

                boost_status = approve_boost_payment(tx_id, dict(request.data))
                if boost_status == 'approved':
                    return Response({'status': 'boost_approved'})
            return Response({'status': 'ignored_unknown_transaction'}, status=status.HTTP_202_ACCEPTED)
        payload = dict(payment.fedapay_payload or {})
        payload['webhook'] = request.data
        payment.fedapay_payload = payload
        if status_value in approved_statuses:
            seat_bundle_pay = _normalized_seat_bundle(payment.promo_bundle)
            catalog = _catalog_entry(payment.plan, payment.billing_cycle, seat_bundle_pay)
            duration_days = int((catalog or {}).get('duration_days') or 30)
            previous_plan = payment.user.profile.subscription_plan
            payment.status = SubscriptionPayment.STATUS_APPROVED
            normalized_wh = _fedapay_normalize_transaction_body(dict(request.data))
            invoice_wh = _extract_invoice_url_from_fedapay(normalized_wh)
            uf = ['status', 'fedapay_payload', 'updated_at']
            if invoice_wh:
                payment.invoice_url = invoice_wh
                uf.append('invoice_url')
            with transaction.atomic():
                payment.save(update_fields=uf)
                SubscriptionConfirmView()._apply_subscription(payment.user.profile, payment, duration_days)
                SubscriptionConfirmView()._notify_payment_events(payment.user, payment, previous_plan)
            return Response({'status': 'approved'})
        if status_value in {'canceled', 'cancelled'}:
            payment.status = SubscriptionPayment.STATUS_CANCELED
        elif status_value in {'failed', 'declined', 'rejected'}:
            payment.status = SubscriptionPayment.STATUS_FAILED
        else:
            payment.status = SubscriptionPayment.STATUS_PENDING
        payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
        return Response({'status': payment.status})


class SupportTicketView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = SupportTicket.objects.filter(user=request.user).order_by('-created_at')[:50]
        return Response({
            'results': [
                {
                    'id': row.id,
                    'subject': row.subject,
                    'message': row.message,
                    'status': row.status,
                    'priority': row.priority,
                    'created_at': row.created_at,
                    'updated_at': row.updated_at,
                }
                for row in rows
            ]
        })

    def post(self, request):
        subject = str(request.data.get('subject') or '').strip()
        message = str(request.data.get('message') or '').strip()
        if len(subject) < 4 or len(message) < 8:
            return Response({'error': 'subject and message are required'}, status=status.HTTP_400_BAD_REQUEST)
        profile = request.user.profile
        priority = (
            SupportTicket.PRIORITY_PRIORITY
            if profile.subscription_plan == Profile.PLAN_PRO
            else SupportTicket.PRIORITY_NORMAL
        )
        ticket = SupportTicket.objects.create(
            user=request.user,
            subject=subject[:140],
            message=message,
            priority=priority,
        )
        return Response({
            'id': ticket.id,
            'subject': ticket.subject,
            'status': ticket.status,
            'priority': ticket.priority,
            'created_at': ticket.created_at,
        }, status=status.HTTP_201_CREATED)


class SubscriptionTrialStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile = request.user.profile
        _enforce_subscription_state(profile)
        if profile.subscription_sponsor_id:
            return Response(
                {'error': 'Compte sur abonnement groupe : impossible de lancer l’essai Plus ici.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if profile.subscription_plan != Profile.PLAN_FREE:
            return Response({'error': 'Trial disponible uniquement depuis le plan Gratuit.'}, status=status.HTTP_400_BAD_REQUEST)
        if profile.subscription_trial_consumed_at is not None:
            return Response({'error': 'Essai déjà utilisé.'}, status=status.HTTP_400_BAD_REQUEST)

        trial_days = _plus_trial_duration_days()
        now = timezone.now()
        profile.subscription_plan = Profile.PLAN_PLUS
        profile.subscription_renewal_at = now + timedelta(days=trial_days)
        profile.subscription_cancel_at_period_end = True
        profile.subscription_scheduled_plan = Profile.PLAN_FREE
        profile.subscription_trial_consumed_at = now
        profile.subscription_seat_bundle = SUBSCRIPTION_BUNDLE_SOLO
        profile.translation_quota_monthly = 100000
        profile.translation_used_monthly = 0
        profile.save(update_fields=[
            'subscription_plan',
            'subscription_renewal_at',
            'subscription_cancel_at_period_end',
            'subscription_scheduled_plan',
            'subscription_trial_consumed_at',
            'subscription_seat_bundle',
            'translation_quota_monthly',
            'translation_used_monthly',
        ])
        create_localized_notification(
            recipient=request.user,
            sender=None,
            notification_type='plan_change',
            title_fr='Essai Plus activé',
            message_fr=(
                f'Vous disposez de {trial_days} jours d\'essai Plus (boards collaboratifs, téléchargements, etc.). '
                'Sans paiement avant la fin : retour automatique au plan Gratuit.'
            ),
            action_url='/premium',
            metadata={'trial_plus_days': trial_days},
        )
        return Response({
            'status': 'trial_started',
            'plan': profile.subscription_plan,
            'trial_days': trial_days,
            'renewal_at': profile.subscription_renewal_at,
        })


class SubscriptionInvoiceListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            SubscriptionPayment.objects.filter(user=request.user)
            .order_by('-created_at')
            [:50]
        )
        items = []
        for row in rows:
            existing = ''
            pd = row.fedapay_payload or {}
            if isinstance(pd, dict):
                norm = pd.get('normalized')
                if isinstance(norm, dict):
                    existing = _extract_invoice_url_from_fedapay(norm)
            items.append({
                'id': row.id,
                'fedapay_transaction_id': row.fedapay_transaction_id,
                'created_at': row.created_at.isoformat(),
                'plan': row.plan,
                'billing_cycle': row.billing_cycle,
                'amount_minor': row.amount,
                'amount_display': _display_amount(row.amount, row.currency_iso),
                'currency_iso': row.currency_iso,
                'promo_bundle': row.promo_bundle or SUBSCRIPTION_BUNDLE_SOLO,
                'status': row.status,
                'checkout_url': row.checkout_url,
                'invoice_url': row.invoice_url or existing,
            })
        return Response({'results': items})


class SubscriptionInvoiceReceiptView(APIView):
    """Récupère (ou recharge) une URL de reçu FedaPay pour une transaction stockée."""

    permission_classes = [permissions.IsAuthenticated]

    def _fedapay_base_url(self):
        env = os.environ.get('FEDAPAY_ENV', 'sandbox').strip().lower()
        if env == 'live':
            return 'https://api.fedapay.com/v1'
        return 'https://sandbox-api.fedapay.com/v1'

    def _fedapay_headers(self):
        secret_key = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
        if not secret_key:
            return None
        return {
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _no_receipt(reason: str, detail: str):
        """Montant payé existe en base mais pas de PDF / URL téléchargeable (≠ facture inexistante)."""
        return Response(
            {'invoice_url': None, 'reason': reason, 'detail': detail},
            status=status.HTTP_200_OK,
        )

    def get(self, request, invoice_id):
        payment = SubscriptionPayment.objects.filter(pk=invoice_id, user=request.user).first()
        if not payment:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.invoice_url:
            return Response({'invoice_url': payment.invoice_url})

        headers = self._fedapay_headers()
        if not headers:
            return Response({'error': 'FedaPay is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        tid = (payment.fedapay_transaction_id or '').strip()
        if not tid or tid.startswith('seed_'):
            return self._no_receipt(
                'no_fedapay_transaction',
                'Aucune transaction passerelle pour ce dossier (identifiant vide, préfixe seed_, ou paiement hors FedaPay).',
            )

        base = self._fedapay_base_url()
        try:
            resp = requests.get(f'{base}/transactions/{tid}', headers=headers, timeout=25)
            if resp.status_code == 404:
                logger.warning(
                    'subscription_invoice_receipt: FedaPay 404 — pk=%s tx=%s vérifiez FEDAPAY_ENV (sandbox vs live)',
                    invoice_id,
                    tid,
                )
                return self._no_receipt(
                    'gateway_transaction_not_found',
                    'Transaction introuvable chez FedaPay — alignez FEDAPAY_SECRET_KEY et '
                    'FEDAPAY_ENV (sandbox/live) avec l’environnement où la transaction a été créée.',
                )
            if resp.status_code >= 400:
                logger.warning(
                    'subscription_invoice_receipt: FedaPay GET failed pk=%s status=%s',
                    invoice_id,
                    resp.status_code,
                )
                return Response(
                    {'error': 'Unable to fetch receipt from gateway', 'upstream_status': resp.status_code},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            tx = resp.json() or {}
        except requests.RequestException as exc:
            logger.exception('subscription_invoice_receipt exception pk=%s', invoice_id)
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        normalized = _fedapay_normalize_transaction_body(tx)
        invoice_url = _extract_invoice_url_from_fedapay(normalized)
        pd = dict(payment.fedapay_payload) if isinstance(payment.fedapay_payload, dict) else {}
        pd['normalized'] = normalized
        pd['receipt_refresh_at'] = timezone.now().isoformat()
        uf = ['fedapay_payload', 'updated_at']
        if invoice_url:
            payment.invoice_url = invoice_url
            uf.append('invoice_url')
        payment.fedapay_payload = pd
        payment.save(update_fields=uf)

        if not invoice_url:
            return self._no_receipt(
                'receipt_missing_in_gateway',
                'La transaction existe chez FedaPay mais aucun lien de reçu / PDF n’a été trouvé dans la réponse.',
            )
        return Response({'invoice_url': invoice_url})


class SubscriptionPricingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        selected_currency, detected_country = _resolve_user_currency(request)
        bundle = _normalized_seat_bundle(request.query_params.get('seat_bundle'))
        pricing_by_bundle = {
            SUBSCRIPTION_BUNDLE_SOLO: _subscription_catalog(selected_currency, SUBSCRIPTION_BUNDLE_SOLO),
            SUBSCRIPTION_BUNDLE_FAMILY: _subscription_catalog(selected_currency, SUBSCRIPTION_BUNDLE_FAMILY),
            SUBSCRIPTION_BUNDLE_TEAM: _subscription_catalog(selected_currency, SUBSCRIPTION_BUNDLE_TEAM),
        }
        plans = pricing_by_bundle.get(bundle, pricing_by_bundle[SUBSCRIPTION_BUNDLE_SOLO])
        return Response({
            'plans': plans,
            'pricing_by_bundle': pricing_by_bundle,
            'annual_discount_percent': _annual_discount_percent_display(),
            'currency': {
                'selected': selected_currency,
                'country_code': detected_country,
                'supported': SUPPORTED_CURRENCIES,
            },
            'seat_bundle': bundle,
            'bundle_discounts': {
                'solo': 0.0,
                'family': 0.0,
                'team': 0.0,
            },
            'seat_invite_limits': {
                'solo': 0,
                'family': SUBSCRIPTION_FAMILY_MAX_INVITEES,
                'team': SUBSCRIPTION_TEAM_MAX_INVITEES,
            },
        })


class CurrencyOptionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        selected_currency, detected_country = _resolve_user_currency(request)
        return Response({
            'supported': SUPPORTED_CURRENCIES,
            'selected': selected_currency,
            'country_code': detected_country,
        })
