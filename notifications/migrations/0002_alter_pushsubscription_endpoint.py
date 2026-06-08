from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pushsubscription',
            name='endpoint',
            field=models.TextField(unique=True),
        ),
    ]
