from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0005_referralcontestsettings'),
        ('contests', '0006_referralcontestsettings_split'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ReferralContestSettings',
        ),
    ]
