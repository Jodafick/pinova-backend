from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0004_pin_promo_campaigns'),
        ('pins', '0004_machinetranslationcache'),
    ]

    operations = [
        migrations.AddField(
            model_name='pinpromocampaign',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='creator_ads/'),
        ),
        migrations.AddField(
            model_name='pinpromocampaign',
            name='cta_label',
            field=models.CharField(blank=True, default='En savoir plus', max_length=40),
        ),
        migrations.AddField(
            model_name='pinpromocampaign',
            name='cta_url',
            field=models.URLField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='pinpromocampaign',
            name='pin',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='promo_campaigns',
                to='pins.pin',
            ),
        ),
    ]
