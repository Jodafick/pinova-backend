"""Vues RGPD — export données, consentement cookies, suppression enrichie."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mail_delivery import EmailDeliveryUnavailable, send_fotoce_mail
from accounts.models import DataExportJob, Profile, UserConsent

logger = logging.getLogger(__name__)

EXPORT_LINK_TTL_HOURS = 24


def _export_download_url(token) -> str:
    base = getattr(settings, 'API_PUBLIC_URL', 'http://localhost:8000').rstrip('/')
    return f'{base}/api/account/export-download/{token}/'


def _send_export_ready_email(user, job: DataExportJob) -> None:
    download_url = _export_download_url(job.download_token)
    try:
        send_fotoce_mail(
            'FOTOCE — votre export de données est prêt',
            (
                'Bonjour,\n\n'
                'Votre archive ZIP (profil, Fotos, commentaires, notifications, abonnements, tips) '
                f'est disponible pendant {EXPORT_LINK_TTL_HOURS} heures :\n\n'
                f'{download_url}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, contactez le support.\n\n'
                '— L’équipe FOTOCE'
            ),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except EmailDeliveryUnavailable:
        logger.warning('Export ready email failed user_id=%s job_id=%s', user.id, job.id)


def _send_deletion_scheduled_email(user, scheduled_at, export_requested: bool) -> None:
    export_line = (
        'Un export de vos données a été lancé en parallèle ; vous recevrez un second e-mail avec le lien de téléchargement.\n\n'
        if export_requested
        else 'Vous pouvez demander un export depuis Paramètres avant la date de purge.\n\n'
    )
    try:
        send_fotoce_mail(
            'FOTOCE — confirmation de suppression de compte',
            (
                'Bonjour,\n\n'
                'Nous confirmons la programmation de la suppression définitive de votre compte FOTOCE.\n'
                f'Date de purge prévue : {scheduled_at.strftime("%Y-%m-%d %H:%M UTC")} '
                '(délai de grâce de 30 jours).\n\n'
                f'{export_line}'
                'Pour annuler, reconnectez-vous et utilisez « Annuler la suppression » dans Paramètres.\n\n'
                '— L’équipe FOTOCE'
            ),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except EmailDeliveryUnavailable:
        logger.warning('Deletion confirmation email failed user_id=%s', user.id)


def _queue_export(user) -> DataExportJob:
    from accounts.tasks import export_user_data

    expires = timezone.now() + timedelta(hours=EXPORT_LINK_TTL_HOURS)
    job = DataExportJob.objects.create(
        user=user,
        status=DataExportJob.STATUS_PENDING,
        download_token=uuid.uuid4(),
        expires_at=expires,
    )
    export_user_data.delay(job.id)
    return job


class AccountExportDataView(APIView):
    """POST /api/account/export-data/ — lance un export async (Celery)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        active = DataExportJob.objects.filter(
            user=request.user,
            status__in=(DataExportJob.STATUS_PENDING, DataExportJob.STATUS_PROCESSING),
        ).exists()
        if active:
            return Response(
                {'detail': 'Un export est déjà en cours.'},
                status=status.HTTP_409_CONFLICT,
            )
        job = _queue_export(request.user)
        job.refresh_from_db()
        payload = {
            'job_id': job.id,
            'status': job.status,
            'expires_at': job.expires_at.isoformat(),
            'message': 'Export lancé. Vous recevrez un e-mail avec le lien de téléchargement.',
        }
        if job.status == DataExportJob.STATUS_READY and job.download_token:
            payload['download_token'] = str(job.download_token)
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class AccountExportDownloadView(APIView):
    """GET /api/account/export-download/<token>/ — téléchargement ZIP (24 h)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            job = DataExportJob.objects.select_related('user').get(download_token=token)
        except DataExportJob.DoesNotExist as exc:
            raise Http404('Export introuvable.') from exc

        if job.status != DataExportJob.STATUS_READY or not job.file_path:
            return Response({'detail': 'Export non disponible.'}, status=status.HTTP_404_NOT_FOUND)
        if job.expires_at and job.expires_at < timezone.now():
            job.status = DataExportJob.STATUS_EXPIRED
            job.save(update_fields=['status'])
            return Response({'detail': 'Lien expiré (24 h).'}, status=status.HTTP_410_GONE)

        if request.user.is_authenticated and request.user.id != job.user_id:
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)

        from pathlib import Path

        full = Path(settings.MEDIA_ROOT) / job.file_path
        if not full.is_file():
            return Response({'detail': 'Fichier absent.'}, status=status.HTTP_404_NOT_FOUND)

        return FileResponse(
            open(full, 'rb'),
            as_attachment=True,
            filename=f'fotoce-export-{job.user_id}.zip',
            content_type='application/zip',
        )


class AccountConsentView(APIView):
    """POST /api/account/consent/ — enregistre le consentement cookies."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        necessary = str(request.data.get('necessary', 'true')).lower() in ('true', '1', 'yes')
        analytics = str(request.data.get('analytics', 'false')).lower() in ('true', '1', 'yes')
        anonymous_id = str(request.data.get('anonymous_id', '') or '').strip()[:64]

        user = request.user if request.user.is_authenticated else None
        if user:
            consent, _ = UserConsent.objects.get_or_create(user=user, defaults={'anonymous_id': anonymous_id})
            consent.necessary = necessary
            consent.analytics = analytics
            if anonymous_id:
                consent.anonymous_id = anonymous_id
            consent.save()
        elif anonymous_id:
            consent, _ = UserConsent.objects.get_or_create(
                anonymous_id=anonymous_id,
                user=None,
                defaults={'necessary': necessary, 'analytics': analytics},
            )
            consent.necessary = necessary
            consent.analytics = analytics
            consent.save()
        else:
            return Response(
                {'anonymous_id': ['Requis pour les visiteurs non connectés.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'necessary': necessary,
                'analytics': analytics,
                'updated_at': timezone.now().isoformat(),
            },
        )

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'analytics': False, 'necessary': True})
        consent = UserConsent.objects.filter(user=request.user).first()
        if not consent:
            return Response({'analytics': False, 'necessary': True})
        return Response(
            {
                'necessary': consent.necessary,
                'analytics': consent.analytics,
                'updated_at': consent.updated_at.isoformat(),
            },
        )
