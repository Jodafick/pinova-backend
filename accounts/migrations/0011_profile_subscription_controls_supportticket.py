from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_update_default_subscription_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='notifications_followers',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notifications_recommendations',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='notifications_saves',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='private_profile',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='subscription_cancel_at_period_end',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='subscription_scheduled_plan',
            field=models.CharField(blank=True, choices=[('free', 'Free'), ('plus', 'Plus'), ('pro', 'Pro')], default='', max_length=20),
        ),
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=140)),
                ('message', models.TextField()),
                ('status', models.CharField(choices=[('open', 'Open'), ('in_progress', 'In progress'), ('resolved', 'Resolved')], default='open', max_length=20)),
                ('priority', models.CharField(choices=[('normal', 'Normal'), ('priority', 'Priority')], default='normal', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_tickets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
