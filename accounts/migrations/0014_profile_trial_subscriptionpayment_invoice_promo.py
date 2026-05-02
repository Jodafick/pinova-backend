from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_profile_birth_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='subscription_trial_consumed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='subscriptionpayment',
            name='invoice_url',
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='subscriptionpayment',
            name='promo_bundle',
            field=models.CharField(blank=True, default='', max_length=24),
        ),
    ]
