from rest_framework import viewsets, status, permissions
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
import os
import requests
from django.db import transaction
import logging

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
from .models import Profile, EmailOTP, SubscriptionPayment, SubscriptionPricing
from .serializers import ProfileSerializer, UserSerializer, RegisterSerializer
from allauth.account.models import EmailAddress
from .currency_utils import (
    SUPPORTED_CURRENCIES,
    convert_minor_amount,
    decimals_for_currency,
    default_currency_for_country,
    infer_country_code,
    normalize_currency,
)

logger = logging.getLogger(__name__)

def _catalog_entry(plan: str, billing_cycle: str):
    row = SubscriptionPricing.objects.filter(
        plan=plan,
        billing_cycle=billing_cycle,
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


def _subscription_catalog(target_currency: str):
    target = normalize_currency(target_currency) or 'XOF'
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
                }
                continue
            values = _catalog_entry(plan, cycle)
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
                # If rate lookup fails, keep original amount/currency to avoid fake prices.
                effective_currency = base_currency
                effective_amount = amount
                conversion_applied = False
            data[plan][cycle] = {
                'amount_minor': effective_amount,
                'amount_display': _display_amount(effective_amount, effective_currency),
                'currency_iso': effective_currency,
                'duration_days': duration_days,
                'source': values.get('source', 'unknown'),
                'base_amount_minor': amount,
                'base_currency_iso': base_currency,
                'conversion_applied': conversion_applied,
            }
    return data


def _display_amount(amount_minor: int, currency_iso: str):
    decimals = decimals_for_currency(currency_iso)
    return amount_minor / (10 ** decimals)

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

            # Valider l'email dans allauth
            email_address, created = EmailAddress.objects.get_or_create(
                user=user, 
                email=email,
                defaults={'verified': True, 'primary': True}
            )
            if not email_address.verified:
                email_address.verified = True
                email_address.save()

            # Créer une notification de bienvenue après validation
            from notifications.models import Notification
            Notification.objects.create(
                recipient=user,
                notification_type='welcome',
                message=f"Bienvenue sur PINOVA, {user.username} ! Votre compte est maintenant validé."
            )

            # Supprimer l'OTP après validation
            otp.delete()

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
            
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                'Nouveau code de validation PINOVA',
                f'Votre nouveau code de validation est : {otp.otp_code}. Il expire dans 10 minutes.',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            return Response({'message': 'Nouveau code envoyé'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable'}, status=status.HTTP_404_NOT_FOUND)

class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    lookup_field = 'user__username'

    def retrieve(self, request, *args, **kwargs):
        profile = self.get_object()
        serializer = UserSerializer(profile.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def follow(self, request, user__username=None):
        profile_to_follow = self.get_object()
        current_user_profile = request.user.profile
        
        if current_user_profile == profile_to_follow:
            return Response({'error': 'You cannot follow yourself'}, status=status.HTTP_400_BAD_REQUEST)
            
        if current_user_profile.following.filter(id=profile_to_follow.id).exists():
            current_user_profile.following.remove(profile_to_follow)
            return Response({'status': 'unfollowed'})
        else:
            current_user_profile.following.add(profile_to_follow)
            # Ici on pourrait créer une notification
            from notifications.models import Notification
            Notification.objects.create(
                recipient=profile_to_follow.user,
                sender=request.user,
                notification_type='follow',
                message=f"{request.user.username} a commencé à vous suivre."
            )
            return Response({'status': 'followed'})

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'profile__display_name']

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def mentions(self, request):
        query = (request.query_params.get('q') or '').strip()
        users = User.objects.select_related('profile').filter(profile__discoverable_profile=True)
        if query:
            users = users.filter(
                models.Q(username__icontains=query) |
                models.Q(profile__display_name__icontains=query)
            )
        users = users.order_by('username')

        class MentionPagination(PageNumberPagination):
            page_size = 10
            page_size_query_param = 'page_size'
            max_page_size = 30

        paginator = MentionPagination()
        page = paginator.paginate_queryset(users, request)
        data = [
            {
                'username': user.username,
                'display_name': user.profile.display_name or user.username,
                'avatar_color': user.profile.avatar_color,
            }
            for user in page
        ]
        return paginator.get_paginated_response(data)

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
        serializer = UserSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        profile = user.profile
        
        # Update user fields
        if 'email' in request.data:
            user.email = request.data['email']
            user.save()
            
        # Plan-based constraints for advertising preferences.
        mutable_data = request.data.copy()
        requested_ad_ads = mutable_data.get('ad_ads_enabled')
        requested_partner_ads = mutable_data.get('partner_ads_enabled')
        if profile.subscription_plan == Profile.PLAN_FREE:
            mutable_data['ad_ads_enabled'] = True
            mutable_data['partner_ads_enabled'] = True
        elif profile.subscription_plan == Profile.PLAN_PLUS:
            if requested_ad_ads is not None:
                mutable_data['ad_ads_enabled'] = requested_ad_ads
            mutable_data['partner_ads_enabled'] = True
        elif profile.subscription_plan == Profile.PLAN_PRO:
            if requested_ad_ads is not None:
                mutable_data['ad_ads_enabled'] = requested_ad_ads
            if requested_partner_ads is not None:
                mutable_data['partner_ads_enabled'] = requested_partner_ads

        # Tips & monetization are reserved for Pro.
        if profile.subscription_plan != Profile.PLAN_PRO:
            mutable_data['tips_enabled'] = False
            mutable_data['tips_url'] = ''

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
            return Response(UserSerializer(user, context={'request': request}).data)
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

        headers = self._fedapay_headers()
        if not headers:
            return Response({'error': 'FedaPay is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        catalog = _catalog_entry(plan, billing_cycle)
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

        callback_url = os.environ.get('FEDAPAY_CALLBACK_URL') or f"{settings.FRONTEND_URL}/premium"
        first_name = request.user.first_name or request.user.profile.display_name or request.user.username
        last_name = request.user.last_name or 'Pinova'

        payload = {
            'description': f"Pinova {plan.title()} ({billing_cycle})",
            'amount': amount,
            'currency': {'iso': currency_iso},
            'callback_url': callback_url,
            'custom_metadata': {
                'user_id': request.user.id,
                'plan': plan,
                'billing_cycle': billing_cycle,
                'duration_days': duration_days,
                'country_code': detected_country,
                'base_amount_minor': base_amount,
                'base_currency_iso': base_currency_iso,
                'target_currency_iso': currency_iso,
                'conversion_applied': conversion_applied,
            },
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
        profile.subscription_plan = payment.plan
        base_start = timezone.now()
        if profile.subscription_renewal_at and profile.subscription_renewal_at > base_start:
            base_start = profile.subscription_renewal_at
        profile.subscription_renewal_at = base_start + timedelta(days=duration_days)
        if payment.plan == Profile.PLAN_FREE:
            profile.translation_quota_monthly = 5
        else:
            profile.translation_quota_monthly = 100000
        profile.translation_used_monthly = 0
        profile.save()

    def post(self, request):
        transaction_id = str(request.data.get('transaction_id') or '').strip()
        if not transaction_id:
            return Response({'error': 'transaction_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = SubscriptionPayment.objects.get(
                fedapay_transaction_id=transaction_id,
                user=request.user,
            )
        except SubscriptionPayment.DoesNotExist:
            return Response({'error': 'Payment session not found'}, status=status.HTTP_404_NOT_FOUND)

        headers = self._fedapay_headers()
        if not headers:
            return Response({'error': 'FedaPay is not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        catalog = _catalog_entry(payment.plan, payment.billing_cycle)
        duration_days = int((catalog or {}).get('duration_days') or 30)
        expected_amount = int(payment.amount)

        base = self._fedapay_base_url()
        try:
            resp = requests.get(f'{base}/transactions/{transaction_id}', headers=headers, timeout=20)
            resp.raise_for_status()
            tx = resp.json() or {}
            paid_amount = self._extract_amount(tx)
            if paid_amount is not None and paid_amount != expected_amount:
                payment.status = SubscriptionPayment.STATUS_FAILED
                payment.fedapay_payload = {'transaction': tx, 'error': 'amount_mismatch'}
                payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
                return Response({
                    'status': 'failed',
                    'error': 'Payment amount mismatch',
                    'expected_amount': expected_amount,
                    'received_amount': paid_amount,
                }, status=status.HTTP_400_BAD_REQUEST)
            status_value = (tx.get('status') or '').strip().lower()
            raw_status = status_value
            if status_value in {'approved', 'success', 'successful', 'completed'}:
                payment.status = SubscriptionPayment.STATUS_APPROVED
                with transaction.atomic():
                    payment.fedapay_payload = {'transaction': tx}
                    payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
                    self._apply_subscription(request.user.profile, payment, duration_days)
                return Response({
                    'status': 'approved',
                    'plan': payment.plan,
                    'billing_cycle': payment.billing_cycle,
                    'duration_days': duration_days,
                    'renewal_at': request.user.profile.subscription_renewal_at,
                })
            if status_value in {'canceled', 'cancelled'}:
                payment.status = SubscriptionPayment.STATUS_CANCELED
            elif status_value in {'failed', 'declined', 'rejected'}:
                payment.status = SubscriptionPayment.STATUS_FAILED
            else:
                payment.status = SubscriptionPayment.STATUS_PENDING
            payment.fedapay_payload = {'transaction': tx}
            payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
            return Response({'status': payment.status, 'gateway_status': raw_status})
        except requests.RequestException as exc:
            return Response({'error': f'FedaPay error: {str(exc)}'}, status=status.HTTP_502_BAD_GATEWAY)


class SubscriptionPricingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        selected_currency, detected_country = _resolve_user_currency(request)
        return Response({
            'plans': _subscription_catalog(selected_currency),
            'currency': {
                'selected': selected_currency,
                'country_code': detected_country,
                'supported': SUPPORTED_CURRENCIES,
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
