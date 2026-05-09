from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0003_referral_antifraud'),
    ]

    operations = [
        migrations.AlterField(
            model_name='referralevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('link_opened', 'Link opened'),
                    ('signup_started', 'Signup started'),
                    ('signup_validated', 'Signup validated'),
                    ('first_login', 'First login'),
                    ('first_post', 'First post'),
                    ('engagement', 'Engagement'),
                    ('retention', 'Retention'),
                    ('retention_progress', 'Retention progress'),
                    ('referral_finalized', 'Referral finalized'),
                    ('reward_deferred', 'Reward deferred'),
                    ('reward_granted', 'Reward granted'),
                    ('fraud_blocked', 'Fraud blocked'),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
