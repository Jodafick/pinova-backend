# Generated manually for PinPromoCampaign

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monetization', '0003_internal_tips'),
        ('pins', '0004_machinetranslationcache'),
    ]

    operations = [
        migrations.CreateModel(
            name='PinPromoCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('headline', models.CharField(blank=True, default='', max_length=120)),
                ('body', models.CharField(blank=True, default='', max_length=400)),
                ('topic_slug', models.CharField(blank=True, default='', max_length=80)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('active', 'Active'),
                        ('paused', 'Paused'),
                        ('expired', 'Expired'),
                        ('canceled', 'Canceled'),
                    ],
                    default='pending',
                    max_length=16,
                )),
                ('starts_at', models.DateTimeField(blank=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('fedapay_transaction_id', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('impressions', models.PositiveIntegerField(default=0)),
                ('clicks', models.PositiveIntegerField(default=0)),
                ('pin_views', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pin_promo_campaigns',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('package', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pin_promo_campaigns',
                    to='monetization.boostpackage',
                )),
                ('pin', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='promo_campaigns',
                    to='pins.pin',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
