# Generated manually for OTP anti brute-force

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_profile_discovery_streak'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailotp',
            name='failed_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
