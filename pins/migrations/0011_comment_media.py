from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0010_topictranslation'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='media',
            field=models.ImageField(blank=True, null=True, upload_to='comments/'),
        ),
    ]
