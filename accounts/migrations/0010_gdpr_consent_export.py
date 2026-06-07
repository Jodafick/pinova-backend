# Generated manually for GDPR consent + export jobs

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0009_profile_retention_prefs'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserConsent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anonymous_id', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('necessary', models.BooleanField(default=True)),
                ('analytics', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cookie_consent',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(user__isnull=False) | ~models.Q(anonymous_id=''),
                        name='userconsent_user_or_anonymous',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='DataExportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('ready', 'Ready'),
                        ('failed', 'Failed'),
                        ('expired', 'Expired'),
                    ],
                    default='pending',
                    max_length=16,
                )),
                ('download_token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('file_path', models.CharField(blank=True, default='', max_length=512)),
                ('error_message', models.CharField(blank=True, default='', max_length=500)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(null=True, blank=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='data_export_jobs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
