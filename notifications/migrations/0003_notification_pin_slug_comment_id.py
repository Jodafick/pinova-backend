from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_notification_notification_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='comment_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='pin_slug',
            field=models.SlugField(blank=True, max_length=255, null=True),
        ),
    ]
