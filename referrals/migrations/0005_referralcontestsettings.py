import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contests', '0006_referralcontestsettings_split'),
        ('referrals', '0004_referralevent_retention_progress_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReferralContestSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'defer_rewards',
                    models.BooleanField(
                        default=True,
                        help_text='Si activé : aucun point parrain tant que le filleul ne passe pas les garde-fous.',
                    ),
                ),
                (
                    'min_account_age_hours',
                    models.PositiveIntegerField(
                        default=12,
                        help_text='Âge minimum du compte filleul (h) avant éligibilité aux points.',
                    ),
                ),
                (
                    'min_engagement_actions',
                    models.PositiveIntegerField(
                        default=1,
                        help_text='Nombre minimum d’interactions concours pins valides du filleul.',
                    ),
                ),
                (
                    'reward_delay_hours',
                    models.PositiveIntegerField(
                        default=1,
                        help_text='Délai minimum après validation du filleul avant éligibilité aux points.',
                    ),
                ),
                (
                    'min_days_before_reward',
                    models.PositiveIntegerField(default=2, help_text='Jours minimum d’activité du filleul avant points parrain.'),
                ),
                (
                    'max_signups_per_ip_per_24h',
                    models.PositiveIntegerField(default=40, help_text='Plafond inscriptions avec IP identique sur 24 h.'),
                ),
                (
                    'max_signups_per_device_per_24h',
                    models.PositiveIntegerField(
                        default=20,
                        help_text='Plafond inscriptions avec empreinte device identique sur 24 h.',
                    ),
                ),
                (
                    'max_referrals_per_referrer_per_24h',
                    models.PositiveIntegerField(
                        default=40,
                        help_text='Plafond nouveaux filleuls attribués au même parrain sur 24 h.',
                    ),
                ),
                (
                    'referee_trust_threshold',
                    models.FloatField(default=0.25, help_text='Trust minimum du filleul (0–1) pour créditer le parrain.'),
                ),
                (
                    'min_pins_published',
                    models.PositiveIntegerField(
                        default=0,
                        help_text='Nombre minimum de pins publics publiés par le filleul (0 = désactivé).',
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'contest',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_settings',
                        to='contests.contestsettings',
                    ),
                ),
            ],
            options={'ordering': ['-contest__contest_key']},
        ),
    ]
