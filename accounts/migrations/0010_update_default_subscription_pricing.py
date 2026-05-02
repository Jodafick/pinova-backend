from django.db import migrations


def update_default_subscription_pricing(apps, schema_editor):
    SubscriptionPricing = apps.get_model('accounts', 'SubscriptionPricing')
    defaults = [
        ('plus', 'monthly', 2000, 30, 'XOF'),
        ('plus', 'yearly', 20000, 365, 'XOF'),
        ('pro', 'monthly', 5000, 30, 'XOF'),
        ('pro', 'yearly', 50000, 365, 'XOF'),
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


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_profile_currency_country'),
    ]

    operations = [
        migrations.RunPython(update_default_subscription_pricing, migrations.RunPython.noop),
    ]
