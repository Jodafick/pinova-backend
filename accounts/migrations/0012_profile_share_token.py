from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_profile_subscription_controls_supportticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='share_token',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]
