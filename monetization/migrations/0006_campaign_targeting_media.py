from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0005_creator_promo_standalone'),
    ]

    operations = [
        migrations.AddField(
            model_name='partnercampaign',
            name='targeting',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='pinpromocampaign',
            name='media',
            field=models.FileField(blank=True, null=True, upload_to='creator_ads/media/'),
        ),
        migrations.AddField(
            model_name='pinpromocampaign',
            name='media_type',
            field=models.CharField(
                choices=[('image', 'Image'), ('video', 'Video')],
                default='image',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='pinpromocampaign',
            name='targeting',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
