# ReferralContestResult payout_json

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='referralcontestresult',
            name='payout_json',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
