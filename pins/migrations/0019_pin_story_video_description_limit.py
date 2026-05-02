# Generated migration — Pin story_video et image optionnelle pour stories vidéo

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0018_board_share_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pin',
            name='description',
            field=models.TextField(blank=True, max_length=1000),
        ),
        migrations.AlterField(
            model_name='pin',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='pins/'),
        ),
        migrations.AddField(
            model_name='pin',
            name='story_video',
            field=models.FileField(blank=True, null=True, upload_to='story_videos/'),
        ),
    ]
