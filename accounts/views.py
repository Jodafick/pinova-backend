from rest_framework import viewsets, status, permissions
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = "http://localhost:5173/login"
    client_class = OAuth2Client

class FacebookLogin(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    callback_url = "http://localhost:5173/login"
    client_class = OAuth2Client
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .models import Profile, EmailOTP
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
            
        # Update profile fields
        profile_serializer = ProfileSerializer(profile, data=request.data, partial=True)
        if profile_serializer.is_valid():
            profile_serializer.save()
            return Response(UserSerializer(user, context={'request': request}).data)
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
