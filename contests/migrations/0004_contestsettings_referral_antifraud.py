from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contests', '0003_contestsettings_leaderboard_display_pins'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestsettings',
            name='referral_defer_rewards',
            field=models.BooleanField(
                default=True,
                help_text='Si activé : aucun point parrain tant que le filleul ne passe pas les garde-fous (âge compte, actions, trust).',
            ),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_min_account_age_hours',
            field=models.PositiveIntegerField(default=24, help_text='Âge minimum du compte filleul (h) avant éligibilité aux points parrain.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_min_engagement_actions',
            field=models.PositiveIntegerField(default=3, help_text='Nombre minimum d’interactions concours pins valides (filleul) pour débloquer la récompense.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_reward_delay_hours',
            field=models.PositiveIntegerField(default=6, help_text='Délai minimum après première activation email du filleul avant éligibilité aux points.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_min_days_before_reward',
            field=models.PositiveIntegerField(default=0, help_text='Jours minimum après activation du parrainage avant points (0 = désactivé).'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_max_signups_per_ip_per_24h',
            field=models.PositiveIntegerField(default=20, help_text='Plafond inscriptions avec contexte IP identique sur 24 h (anti mass signup).'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_max_signups_per_device_per_24h',
            field=models.PositiveIntegerField(default=8, help_text='Plafond inscriptions avec même empreinte device sur 24 h.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_max_referrals_per_referrer_per_24h',
            field=models.PositiveIntegerField(default=40, help_text='Plafond nouveaux filleuls attribués au même parrain sur 24 h.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_referee_trust_threshold',
            field=models.FloatField(default=0.35, help_text='Trust minimum du filleul (0–1) pour créditer le parrain.'),
        ),
        migrations.AddField(
            model_name='contestsettings',
            name='referral_min_pins_published',
            field=models.PositiveIntegerField(default=0, help_text='Nombre minimum de pins publics publiés par le filleul (0 = désactivé).'),
        ),
    ]
