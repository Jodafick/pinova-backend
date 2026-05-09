import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def forwards_backfill_rewards_granted(apps, schema_editor):
    ReferralEvent = apps.get_model('referrals', 'ReferralEvent')
    ReferralAttribution = apps.get_model('referrals', 'ReferralAttribution')
    now = django.utils.timezone.now()
    for ev in ReferralEvent.objects.filter(event_type='referral_finalized', is_valid=True).exclude(score_delta=0.0):
        rid = getattr(ev, 'referee_id', None)
        if rid:
            ReferralAttribution.objects.filter(referee_id=rid, rewards_granted_at__isnull=True).update(rewards_granted_at=now)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0002_referralcontestresult'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='referralattribution',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='referralattribution',
            name='rewards_granted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='referralattribution',
            name='signup_ip',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='referralattribution',
            name='signup_device_hash',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.CreateModel(
            name='ReferralSignupContext',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signup_ip', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('device_hash', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('user_agent_snippet', models.CharField(blank=True, default='', max_length=256)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_signup_context',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name='referralsignupcontext',
            index=models.Index(fields=['signup_ip', '-created_at'], name='ref_signup_ip_idx'),
        ),
        migrations.AddIndex(
            model_name='referralsignupcontext',
            index=models.Index(fields=['device_hash', '-created_at'], name='ref_signup_dev_idx'),
        ),
        migrations.CreateModel(
            name='UserReferralTrust',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.FloatField(db_index=True, default=0.5)),
                ('signals_json', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_trust_profile',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='ReferralAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(db_index=True, max_length=64)),
                ('ip', models.CharField(blank=True, default='', max_length=64)),
                ('device_hash', models.CharField(blank=True, default='', max_length=128)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    'attribution',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='audit_logs',
                        to='referrals.referralattribution',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='referral_audit_logs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ReferralSuspicionFlag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=64)),
                ('severity', models.PositiveSmallIntegerField(default=1, help_text='1=info, 5=critique')),
                (
                    'status',
                    models.CharField(
                        choices=[('open', 'Open'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')],
                        db_index=True,
                        default='open',
                        max_length=16,
                    ),
                ),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                (
                    'attribution',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='suspicion_flags',
                        to='referrals.referralattribution',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_suspicion_flags',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='referralsuspicionflag',
            index=models.Index(fields=['status', '-created_at'], name='ref_susp_st_idx'),
        ),
        migrations.RunPython(forwards_backfill_rewards_granted, backwards_noop),
    ]
