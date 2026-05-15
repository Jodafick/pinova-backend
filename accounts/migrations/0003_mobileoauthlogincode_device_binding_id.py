from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_mobileoauthlogincode'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileoauthlogincode',
            name='device_binding_id',
            field=models.CharField(db_index=True, default='', max_length=128),
            preserve_default=False,
        ),
    ]
