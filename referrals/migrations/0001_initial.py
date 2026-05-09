# Generated manually for referrals app

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contests', '0003_contestsettings_leaderboard_display_pins'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserReferralCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, editable=False, max_length=16, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_code_row',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ReferralPendingIntent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('device_binding_id', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('code_normalized', models.CharField(db_index=True, max_length=32)),
                ('utm_json', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='referralpendingintent',
            constraint=models.CheckConstraint(
                check=~(models.Q(session_key='') & models.Q(device_binding_id='')),
                name='referral_intent_session_or_device',
            ),
        ),
        migrations.AddIndex(
            model_name='referralpendingintent',
            index=models.Index(fields=['session_key', '-created_at'], name='ref_pending_sess_idx'),
        ),
        migrations.AddIndex(
            model_name='referralpendingintent',
            index=models.Index(fields=['device_binding_id', '-created_at'], name='ref_pending_dev_idx'),
        ),
        migrations.CreateModel(
            name='ReferralAttribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending_email', 'Pending email verification'),
                            ('active', 'Active'),
                            ('revoked', 'Revoked'),
                        ],
                        db_index=True,
                        default='pending_email',
                        max_length=24,
                    ),
                ),
                (
                    'source',
                    models.CharField(
                        choices=[
                            ('link_query', 'Link query'),
                            ('deep_link', 'Deep link'),
                            ('signup_field', 'Signup field'),
                            ('intent_api', 'Intent API'),
                            ('oauth_completion', 'OAuth completion'),
                            ('onboarding_modal', 'Onboarding modal'),
                        ],
                        default='signup_field',
                        max_length=32,
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('activated_at', models.DateTimeField(blank=True, null=True)),
                (
                    'referee',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_attribution',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'referrer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referrals_given',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name='referralattribution',
            index=models.Index(fields=['referrer', 'status'], name='ref_attr_referrer_idx'),
        ),
        migrations.CreateModel(
            name='ReferralEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'event_type',
                    models.CharField(
                        choices=[
                            ('link_opened', 'Link opened'),
                            ('signup_started', 'Signup started'),
                            ('signup_validated', 'Signup validated'),
                            ('first_login', 'First login'),
                            ('first_post', 'First post'),
                            ('engagement', 'Engagement'),
                            ('retention', 'Retention'),
                            ('referral_finalized', 'Referral finalized'),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('is_valid', models.BooleanField(db_index=True, default=True)),
                ('invalid_reason', models.CharField(blank=True, default='', max_length=120)),
                ('score_delta', models.FloatField(default=0.0)),
                ('trust_score', models.FloatField(default=1.0)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    'contest',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='referral_events',
                        to='contests.contestsettings',
                    ),
                ),
                (
                    'referee',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_events_as_referee',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'referrer',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_events_as_referrer',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='referralevent',
            index=models.Index(fields=['contest', 'event_type', '-created_at'], name='ref_evt_contest_idx'),
        ),
        migrations.AddIndex(
            model_name='referralevent',
            index=models.Index(fields=['referrer', '-created_at'], name='ref_evt_referrer_idx'),
        ),
        migrations.CreateModel(
            name='ReferrerReferralScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_score', models.FloatField(db_index=True, default=0.0)),
                ('rank', models.PositiveIntegerField(db_index=True, default=0)),
                ('previous_rank', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'contest',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referrer_referral_scores',
                        to='contests.contestsettings',
                    ),
                ),
                (
                    'referrer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referrer_referral_scores',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['rank', '-total_score'], 'unique_together': {('contest', 'referrer')}},
        ),
        migrations.CreateModel(
            name='ReferralLeaderboardEvent',
            fields=[
                ('sequence', models.BigAutoField(primary_key=True, serialize=False)),
                ('event_type', models.CharField(db_index=True, max_length=32)),
                ('entity_id', models.PositiveIntegerField(db_index=True)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    'contest',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_leaderboard_events',
                        to='contests.contestsettings',
                    ),
                ),
            ],
            options={'ordering': ['sequence']},
        ),
    ]
