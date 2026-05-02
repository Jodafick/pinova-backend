from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_subscriptionpricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='country_code',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
        migrations.AddField(
            model_name='profile',
            name='preferred_currency',
            field=models.CharField(default='XOF', max_length=3),
        ),
    ]
