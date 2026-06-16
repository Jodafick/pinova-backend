from django.db import migrations, models

_LEGACY_MAP = {
    'harassment': 'harmful',
    'hate': 'harmful',
    'sexual': 'harmful',
    'violence': 'harmful',
    'illegal': 'harmful',
    'minor': 'harmful',
    'spam': 'spam_scam',
    'impersonation': 'spam_scam',
    'copyright': 'spam_scam',
    'other': 'other',
}


def migrate_report_categories(apps, schema_editor):
    ContentReport = apps.get_model('fotos', 'ContentReport')
    for row in ContentReport.objects.all().only('id', 'category'):
        mapped = _LEGACY_MAP.get(row.category, 'other')
        if mapped != row.category:
            row.category = mapped
            row.save(update_fields=['category'])


class Migration(migrations.Migration):
    dependencies = [
        ('fotos', '0004_machinetranslationcache'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentreport',
            name='category',
            field=models.CharField(
                choices=[
                    ('harmful', 'Contenu préjudiciable'),
                    ('spam_scam', 'Spam, arnaque ou usurpation'),
                    ('other', 'Autre'),
                ],
                default='other',
                max_length=32,
            ),
        ),
        migrations.RunPython(migrate_report_categories, migrations.RunPython.noop),
    ]
