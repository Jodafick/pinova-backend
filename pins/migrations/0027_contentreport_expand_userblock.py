# Generated manually — signalements enrichis (profil / catégorie / détails)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def forwards_copy_reason_to_details(apps, schema_editor):
    ContentReport = apps.get_model('pins', 'ContentReport')
    for row in ContentReport.objects.all().iterator():
        reason = (getattr(row, 'reason', None) or '')[:2000]
        if reason:
            ContentReport.objects.filter(pk=row.pk).update(details=reason)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pins', '0026_clear_story_expiry_non_ephemeral'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentreport',
            name='details',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='contentreport',
            name='category',
            field=models.CharField(
                choices=[
                    ('spam', 'Spam ou publicité'),
                    ('harassment', 'Harcèlement ou intimidation'),
                    ('hate', 'Haine ou discrimination'),
                    ('sexual', 'Contenu sexuel ou nudité non autorisée'),
                    ('violence', 'Violence ou danger'),
                    ('illegal', 'Activité illégale'),
                    ('minor', 'Sécurité des mineurs'),
                    ('impersonation', 'Usurpation ou arnaque'),
                    ('copyright', 'Propriété intellectuelle'),
                    ('other', 'Autre'),
                ],
                default='other',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='contentreport',
            name='reported_user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='profile_reports_received',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(forwards_copy_reason_to_details, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='contentreport',
            index=models.Index(fields=['reported_user', '-created_at'], name='pins_conten_reporte_idx'),
        ),
        migrations.AddConstraint(
            model_name='contentreport',
            constraint=models.CheckConstraint(
                condition=(
                    Q(pin__isnull=False, comment__isnull=True, reported_user__isnull=True)
                    | Q(pin__isnull=True, comment__isnull=False, reported_user__isnull=True)
                    | Q(pin__isnull=True, comment__isnull=True, reported_user__isnull=False)
                ),
                name='contentreport_exactly_one_target',
            ),
        ),
        migrations.AddConstraint(
            model_name='contentreport',
            constraint=models.UniqueConstraint(
                fields=('reporter', 'reported_user'),
                condition=Q(reported_user__isnull=False),
                name='contentreport_unique_profile_per_reporter',
            ),
        ),
    ]
