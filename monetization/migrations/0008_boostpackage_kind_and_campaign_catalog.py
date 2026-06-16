from django.db import migrations, models


def migrate_catalog(apps, schema_editor):
    BoostPackage = apps.get_model('monetization', 'BoostPackage')
    legacy = {
        '24h': ('boost', 'Boost 24 h', 24, 1500),
        '72h': ('boost', 'Boost 3 jours', 72, 3500),
        '7d': ('boost', 'Boost 7 jours', 168, 7500),
    }
    for slug, (kind, label, hours, amount) in legacy.items():
        BoostPackage.objects.update_or_create(
            slug=slug,
            defaults={
                'label': label,
                'package_kind': kind,
                'duration_hours': hours,
                'amount': amount,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )
    campaign_specs = [
        ('campaign-24h', 'Campagne 24 h', 24, 2500),
        ('campaign-72h', 'Campagne 3 jours', 72, 5500),
        ('campaign-7d', 'Campagne 7 jours', 168, 11500),
    ]
    for slug, label, hours, amount in campaign_specs:
        BoostPackage.objects.update_or_create(
            slug=slug,
            defaults={
                'label': label,
                'package_kind': 'campaign',
                'duration_hours': hours,
                'amount': amount,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0007_webhookeventprocessed'),
    ]

    operations = [
        migrations.AddField(
            model_name='boostpackage',
            name='package_kind',
            field=models.CharField(
                choices=[('boost', 'Boost foto'), ('campaign', 'Campagne pub'), ('both', 'Boost et campagne')],
                db_index=True,
                default='both',
                help_text='Restreint l’usage du pack (boost, campagne pub, ou les deux).',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='boostpackage',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterModelOptions(
            name='boostpackage',
            options={'ordering': ['package_kind', 'duration_hours']},
        ),
        migrations.RunPython(migrate_catalog, migrations.RunPython.noop),
    ]
