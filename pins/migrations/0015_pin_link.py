from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0014_topic_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='link',
            field=models.URLField(blank=True, default=''),
        ),
    ]
