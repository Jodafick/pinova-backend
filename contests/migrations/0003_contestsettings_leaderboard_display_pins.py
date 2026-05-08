from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ('contests', '0002_contestsettings_notify_leaderboard_rank_changes'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestsettings',
            name='leaderboard_display_pins',
            field=models.PositiveSmallIntegerField(
                default=10,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(500),
                ],
                help_text='Pins shown on the live leaderboard (one row per creator, best pin). Caps the public pins API.',
            ),
        ),
    ]
