"""
Envoie le digest créateur Pro (vues semaine + push + e-mail).

Planifier (exemple) : lundi 9h UTC — crontab
  0 9 * * 1 django-admin send_weekly_pro_digest
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

from accounts.models import Profile
from pins.weekly_stats import pro_weekly_views_stats
from notifications.notification_i18n import create_localized_notification


class Command(BaseCommand):
    help = 'Envoie digest hebdomadaire Pro : pins les plus vus (PinViewEvent 7 derniers jours).'

    def handle(self, *args, **options):
        base_url = str(getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        qs = Profile.objects.filter(
            subscription_plan=Profile.PLAN_PRO,
            notifications_digest_creator_weekly=True,
        ).select_related('user')
        sent = 0
        skipped = 0
        for profile in qs:
            user = profile.user
            email = (user.email or '').strip()
            if not email:
                skipped += 1
                continue
            pins_ranked, total_events = pro_weekly_views_stats(user, days=7)
            top = pins_ranked[:10]
            if total_events <= 0 or not top:
                skipped += 1
                continue
            lang = (profile.preferred_language or 'fr').lower().split('-')[0]
            lines_body = []
            if lang.startswith('fr'):
                lines_body.append('Voici vos contenus ayant reçu le plus de vues sur les 7 derniers jours :')
                lines_body.append('')
            else:
                lines_body.append('Here are your pins with the most views in the last 7 days:')
                lines_body.append('')
            for i, pin in enumerate(top, 1):
                vw = int(getattr(pin, 'views_week', 0))
                pin_url = f'{base_url}/pin/{pin.slug}' if base_url else f'/pin/{pin.slug}'
                unit = 'vues' if lang.startswith('fr') else 'views'
                lines_body.append(f'{i}. {pin.title[:120]} — {vw} {unit} — {pin_url}')
            body = '\n'.join(lines_body)
            pin0 = top[0]
            v0 = int(getattr(pin0, 'views_week', 0))
            digest_message_fr = (
                f'Top : {pin0.title[:70]} (+{len(top)-1} autres)'
                if len(top) > 1
                else f'{pin0.title[:90]} — {v0} v.'
            )[:255]

            create_localized_notification(
                recipient=user,
                sender=None,
                notification_type='digest',
                title_fr='Vos pins les plus vus cette semaine',
                message_fr=digest_message_fr,
                action_url='/creator',
                metadata={'digest': 'weekly_views', 'days': 7},
            )

            subject_fr = '[Pinova Pro] Ton récap’ de la semaine'
            subject_en = '[Pinova Pro] Your weekly recap'
            subject = subject_fr if lang.startswith('fr') else subject_en
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or None
            try:
                send_mail(subject, body, from_email, [email], fail_silently=False)
                sent += 1
                self.stdout.write(self.style.SUCCESS(f'sent digest user_id={user.id}'))
            except Exception as exc:
                skipped += 1
                self.stderr.write(self.style.ERROR(f'mail_fail user_id={user.id}: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'Done: sent={sent} skipped_or_empty={skipped}'))
