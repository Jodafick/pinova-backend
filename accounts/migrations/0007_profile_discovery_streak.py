from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0006_profile_ad_preferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='discovery_streak_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='profile',
            name='discovery_streak_best',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='profile',
            name='discovery_streak_last_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
