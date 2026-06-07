from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_emailotp_failed_attempts'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='discovery_streak_reminder_sent_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notifications_streak_reminders',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notifications_reactivation_emails',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='retention_j7_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='retention_j30_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
