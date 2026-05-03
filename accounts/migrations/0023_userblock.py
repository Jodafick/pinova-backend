# Generated manually — blocage de profils

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0022_profile_hide_sensitive_pins'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'blocked',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='user_blocks_received',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'blocker',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='user_blocks_made',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='userblock',
            constraint=models.UniqueConstraint(fields=('blocker', 'blocked'), name='uniq_userblock_blocker_blocked'),
        ),
        migrations.AddConstraint(
            model_name='userblock',
            constraint=models.CheckConstraint(
                check=~Q(blocker_id=F('blocked_id')),
                name='userblock_no_self',
            ),
        ),
        migrations.AddIndex(
            model_name='userblock',
            index=models.Index(fields=['blocker', '-created_at'], name='accounts_us_blocker_7a8b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='userblock',
            index=models.Index(fields=['blocked', '-created_at'], name='accounts_us_blocked_9d0e1f_idx'),
        ),
    ]
