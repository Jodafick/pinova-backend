from django.db import migrations, models


def relax_existing_contests(apps, schema_editor):
    ContestSettings = apps.get_model('contests', 'ContestSettings')
    for cs in ContestSettings.objects.all():
        changed = False
        if cs.referral_min_account_age_hours >= 24:
            cs.referral_min_account_age_hours = 12
            changed = True
        if cs.referral_min_engagement_actions >= 3:
            cs.referral_min_engagement_actions = 1
            changed = True
        if cs.referral_reward_delay_hours >= 6:
            cs.referral_reward_delay_hours = 1
            changed = True
        if cs.referral_min_days_before_reward <= 0:
            cs.referral_min_days_before_reward = 2
            changed = True
        if cs.referral_max_signups_per_ip_per_24h <= 20:
            cs.referral_max_signups_per_ip_per_24h = 40
            changed = True
        if cs.referral_max_signups_per_device_per_24h <= 8:
            cs.referral_max_signups_per_device_per_24h = 20
            changed = True
        if cs.referral_referee_trust_threshold >= 0.35:
            cs.referral_referee_trust_threshold = 0.25
            changed = True
        if changed:
            cs.save(
                update_fields=[
                    'referral_min_account_age_hours',
                    'referral_min_engagement_actions',
                    'referral_reward_delay_hours',
                    'referral_min_days_before_reward',
                    'referral_max_signups_per_ip_per_24h',
                    'referral_max_signups_per_device_per_24h',
                    'referral_referee_trust_threshold',
                ]
            )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('contests', '0004_contestsettings_referral_antifraud'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_min_account_age_hours',
            field=models.PositiveIntegerField(default=12, help_text='Âge minimum du compte filleul (h) avant éligibilité aux points parrain.'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_min_engagement_actions',
            field=models.PositiveIntegerField(default=1, help_text='Nombre minimum d’interactions concours pins valides (filleul) pour débloquer la récompense.'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_reward_delay_hours',
            field=models.PositiveIntegerField(default=1, help_text='Délai minimum après première activation email du filleul avant éligibilité aux points.'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_min_days_before_reward',
            field=models.PositiveIntegerField(default=2, help_text='Jours minimum après activation du parrainage avant points (0 = désactivé).'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_max_signups_per_ip_per_24h',
            field=models.PositiveIntegerField(default=40, help_text='Plafond inscriptions avec contexte IP identique sur 24 h (anti mass signup).'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_max_signups_per_device_per_24h',
            field=models.PositiveIntegerField(default=20, help_text='Plafond inscriptions avec même empreinte device sur 24 h.'),
        ),
        migrations.AlterField(
            model_name='contestsettings',
            name='referral_referee_trust_threshold',
            field=models.FloatField(default=0.25, help_text='Trust minimum du filleul (0–1) pour créditer le parrain.'),
        ),
        migrations.RunPython(relax_existing_contests, noop_reverse),
    ]
