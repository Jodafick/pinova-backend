from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_mobileoauthlogincode_device_binding_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileoauthlogincode',
            name='mobile_state_hash',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
