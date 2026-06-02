from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_profile_extended_onboarding'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='ad_ads_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='partner_ads_enabled',
            field=models.BooleanField(default=True),
        ),
    ]
