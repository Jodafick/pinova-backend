from django.db import migrations


def enable_ads_for_all(apps, schema_editor):
    Profile = apps.get_model('accounts', 'Profile')
    Profile.objects.update(ad_ads_enabled=True, partner_ads_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_gdpr_consent_export'),
    ]

    operations = [
        migrations.RunPython(enable_ads_for_all, migrations.RunPython.noop),
    ]
