from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_profile_trial_subscriptionpayment_invoice_promo'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='notifications_digest_creator_weekly',
            field=models.BooleanField(default=True),
        ),
    ]
