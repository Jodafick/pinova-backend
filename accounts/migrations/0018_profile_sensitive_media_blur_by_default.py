# Generated manually for PRESTIGE

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_subscription_seats'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='sensitive_media_blur_by_default',
            field=models.BooleanField(default=True),
        ),
    ]
