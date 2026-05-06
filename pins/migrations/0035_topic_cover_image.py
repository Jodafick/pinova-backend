# Generated manually for Topic.cover_image

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0034_rename_pins_proces_user_id_d46ce5_idx_pins_proces_user_id_09780b_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='topic_covers/'),
        ),
    ]
