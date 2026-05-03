# Generated manually for ephemeral premium stories.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0024_remove_pin_pins_pin_sched_pub_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='story_ephemeral',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
