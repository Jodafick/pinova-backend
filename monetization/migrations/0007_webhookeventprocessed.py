# Generated manually — idempotence webhooks FedaPay

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0006_campaign_targeting_media'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookEventProcessed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_id', models.CharField(db_index=True, max_length=64)),
                ('event_type', models.CharField(max_length=64)),
                ('processed_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-processed_at'],
                'indexes': [
                    models.Index(fields=['transaction_id', 'event_type'], name='monetization_tx_evt_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('transaction_id', 'event_type'),
                        name='monetization_webhook_event_unique',
                    ),
                ],
            },
        ),
    ]
