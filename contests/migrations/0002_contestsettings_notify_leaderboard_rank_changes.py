from django.db import migrations, models


def sync_rank_notify_from_top10(apps, schema_editor):
    ContestSettings = apps.get_model('contests', 'ContestSettings')
    for row in ContestSettings.objects.iterator():
        row.notify_leaderboard_rank_changes = row.notify_top_10
        row.save(update_fields=['notify_leaderboard_rank_changes'])


class Migration(migrations.Migration):
    dependencies = [
        ('contests', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestsettings',
            name='notify_leaderboard_rank_changes',
            field=models.BooleanField(
                default=True,
                help_text='Notify creators when their displayed contest rank (best pin) changes; uses anti-spam throttling.',
            ),
        ),
        migrations.RunPython(sync_rank_notify_from_top10, migrations.RunPython.noop),
    ]
