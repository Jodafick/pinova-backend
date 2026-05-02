from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0021_moderation_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='media_sensitive_blur',
            field=models.BooleanField(default=False),
        ),
    ]
