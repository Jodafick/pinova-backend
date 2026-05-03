# Generated manually for duplicate report prevention

from django.db import migrations, models
from django.db.models import Q


def dedupe_pin_comment_reports(apps, schema_editor):
    ContentReport = apps.get_model('pins', 'ContentReport')
    seen_pin = set()
    seen_comment = set()
    to_delete = []
    for row in ContentReport.objects.order_by('id').iterator():
        if row.pin_id:
            key = (row.reporter_id, row.pin_id)
            if key in seen_pin:
                to_delete.append(row.pk)
            else:
                seen_pin.add(key)
        elif row.comment_id:
            key = (row.reporter_id, row.comment_id)
            if key in seen_comment:
                to_delete.append(row.pk)
            else:
                seen_comment.add(key)
    if to_delete:
        ContentReport.objects.filter(pk__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0028_rename_pins_conten_reporte_idx_pins_conten_reporte_4034bf_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe_pin_comment_reports, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='contentreport',
            constraint=models.UniqueConstraint(
                condition=Q(pin__isnull=False),
                fields=('reporter', 'pin'),
                name='contentreport_unique_pin_per_reporter',
            ),
        ),
        migrations.AddConstraint(
            model_name='contentreport',
            constraint=models.UniqueConstraint(
                condition=Q(comment__isnull=False),
                fields=('reporter', 'comment'),
                name='contentreport_unique_comment_per_reporter',
            ),
        ),
    ]
