from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_enable_ads_for_all_profiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='activation_funnel_json',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
