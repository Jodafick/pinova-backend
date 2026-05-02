from django.db import migrations, models


def seed_subscription_pricing(apps, schema_editor):
    SubscriptionPricing = apps.get_model('accounts', 'SubscriptionPricing')
    defaults = [
        ('plus', 'monthly', 499, 30, 'XOF'),
        ('plus', 'yearly', 4900, 365, 'XOF'),
        ('pro', 'monthly', 1299, 30, 'XOF'),
        ('pro', 'yearly', 12900, 365, 'XOF'),
    ]
    for plan, billing_cycle, amount, duration_days, currency_iso in defaults:
        SubscriptionPricing.objects.update_or_create(
            plan=plan,
            billing_cycle=billing_cycle,
            defaults={
                'amount': amount,
                'duration_days': duration_days,
                'currency_iso': currency_iso,
                'is_active': True,
            },
        )


def unseed_subscription_pricing(apps, schema_editor):
    SubscriptionPricing = apps.get_model('accounts', 'SubscriptionPricing')
    SubscriptionPricing.objects.filter(
        plan__in=['plus', 'pro'],
        billing_cycle__in=['monthly', 'yearly'],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_subscriptionpayment'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPricing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('free', 'Free'), ('plus', 'Plus'), ('pro', 'Pro')], max_length=20)),
                ('billing_cycle', models.CharField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly', max_length=20)),
                ('amount', models.PositiveIntegerField()),
                ('duration_days', models.PositiveIntegerField(default=30)),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['plan', 'billing_cycle'],
                'unique_together': {('plan', 'billing_cycle')},
            },
        ),
        migrations.RunPython(seed_subscription_pricing, unseed_subscription_pricing),
    ]
