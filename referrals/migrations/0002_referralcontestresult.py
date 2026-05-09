import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReferralContestResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('winners_json', models.JSONField(blank=True, default=list)),
                ('leaderboard_snapshot_json', models.JSONField(blank=True, default=list)),
                ('stats_json', models.JSONField(blank=True, default=dict)),
                ('finalized_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    'contest',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='referral_result',
                        to='contests.contestsettings',
                    ),
                ),
            ],
            options={'ordering': ['-finalized_at']},
        ),
    ]
