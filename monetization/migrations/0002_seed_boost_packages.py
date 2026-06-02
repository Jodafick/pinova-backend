from django.db import migrations


def seed_packages(apps, schema_editor):
    BoostPackage = apps.get_model('monetization', 'BoostPackage')
    defaults = [
        ('24h', 'Boost 24 h', 24, 1500),
        ('72h', 'Boost 3 jours', 72, 3500),
        ('7d', 'Boost 7 jours', 168, 7500),
    ]
    for slug, label, hours, amount in defaults:
        BoostPackage.objects.update_or_create(
            slug=slug,
            defaults={
                'label': label,
                'duration_hours': hours,
                'amount': amount,
                'currency_iso': 'XOF',
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_packages, migrations.RunPython.noop),
    ]
