from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_profile_notifications_digest_creator_weekly'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='account_scheduled_deletion_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
