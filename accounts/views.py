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
from .models import Profile, EmailOTP, SubscriptionPayment
from .serializers import ProfileSerializer, UserSerializer, RegisterSerializer
from allauth.account.models import EmailAddress

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

        # Update profile fields
        profile_serializer = ProfileSerializer(profile, data=mutable_data, partial=True)
        if profile_serializer.is_valid():
            profile_serializer.save()
            return Response(UserSerializer(user, context={'request': request}).data)
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    PRICE_MAP_XOF = {
        'plus': {'monthly': 499, 'yearly': 4900},
        'pro': {'monthly': 1299, 'yearly': 12900},
    }

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

    def _get_amount(self, plan, billing_cycle):
        return self.PRICE_MAP_XOF.get(plan, {}).get(billing_cycle)

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

        amount = self._get_amount(plan, billing_cycle)
        if not amount:
            return Response({'error': 'Unsupported pricing configuration'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        callback_url = os.environ.get('FEDAPAY_CALLBACK_URL') or f"{settings.FRONTEND_URL}/premium"
        first_name = request.user.first_name or request.user.profile.display_name or request.user.username
        last_name = request.user.last_name or 'Pinova'

        payload = {
            'description': f"Pinova {plan.title()} ({billing_cycle})",
            'amount': amount,
            'currency': {'iso': os.environ.get('FEDAPAY_CURRENCY_ISO', 'XOF')},
            'callback_url': callback_url,
            'custom_metadata': {
                'user_id': request.user.id,
                'plan': plan,
                'billing_cycle': billing_cycle,
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
            create_resp.raise_for_status()
            transaction_data = create_resp.json() or {}
            transaction_id = transaction_data.get('id')
            if not transaction_id:
                return Response({'error': 'Invalid FedaPay transaction response'}, status=status.HTTP_502_BAD_GATEWAY)

            token_resp = requests.post(f'{base}/transactions/{transaction_id}/token', headers=headers, timeout=20)
            token_resp.raise_for_status()
            token_data = token_resp.json() or {}
            checkout_url = token_data.get('url') or token_data.get('payment_url')
            if not checkout_url:
                return Response({'error': 'Unable to generate checkout URL'}, status=status.HTTP_502_BAD_GATEWAY)

            SubscriptionPayment.objects.update_or_create(
                fedapay_transaction_id=str(transaction_id),
                defaults={
                    'user': request.user,
                    'plan': plan,
                    'billing_cycle': billing_cycle,
                    'amount': amount,
                    'currency_iso': os.environ.get('FEDAPAY_CURRENCY_ISO', 'XOF'),
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
            }, status=status.HTTP_201_CREATED)
        except requests.RequestException as exc:
            return Response({'error': f'FedaPay error: {str(exc)}'}, status=status.HTTP_502_BAD_GATEWAY)


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

    def _apply_subscription(self, profile, payment):
        profile.subscription_plan = payment.plan
        now = timezone.now()
        duration_days = 365 if payment.billing_cycle == SubscriptionPayment.BILLING_YEARLY else 30
        profile.subscription_renewal_at = now + timedelta(days=duration_days)
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

        base = self._fedapay_base_url()
        try:
            resp = requests.get(f'{base}/transactions/{transaction_id}', headers=headers, timeout=20)
            resp.raise_for_status()
            tx = resp.json() or {}
            status_value = (tx.get('status') or '').strip().lower()
            raw_status = status_value
            if status_value in {'approved', 'success', 'successful', 'completed'}:
                payment.status = SubscriptionPayment.STATUS_APPROVED
                with transaction.atomic():
                    payment.fedapay_payload = {'transaction': tx}
                    payment.save(update_fields=['status', 'fedapay_payload', 'updated_at'])
                    self._apply_subscription(request.user.profile, payment)
                return Response({'status': 'approved', 'plan': payment.plan})
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
