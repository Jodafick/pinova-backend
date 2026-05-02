# Generated manually for creator comment moderation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0019_pin_story_video_description_limit'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='comments_policy',
            field=models.CharField(
                choices=[
                    ('open', 'Open'),
                    ('followers_only', 'Followers only'),
                    ('closed', 'Closed'),
                ],
                default='open',
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='comment',
            name='hidden_by_owner',
            field=models.BooleanField(default=False),
        ),
    ]
