from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0017_pin_variant_story'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='share_token',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]
