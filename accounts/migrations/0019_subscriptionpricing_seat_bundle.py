from django.db import migrations, models


def seed_official_pricing(apps, schema_editor):
    SP = apps.get_model('accounts', 'SubscriptionPricing')
    SP.objects.filter(plan__in=('plus', 'pro')).delete()
    rows = [
        ('plus', 'monthly', 'solo', 1500, 30),
        ('plus', 'yearly', 'solo', 16200, 365),
        ('plus', 'monthly', 'family', 4500, 30),
        ('plus', 'yearly', 'family', 48600, 365),
        ('plus', 'monthly', 'team', 12000, 30),
        ('plus', 'yearly', 'team', 129600, 365),
        ('pro', 'monthly', 'solo', 2500, 30),
        ('pro', 'yearly', 'solo', 27000, 365),
        ('pro', 'monthly', 'family', 7500, 30),
        ('pro', 'yearly', 'family', 81000, 365),
        ('pro', 'monthly', 'team', 20000, 30),
        ('pro', 'yearly', 'team', 216000, 365),
    ]
    for plan, billing_cycle, seat_bundle, amount, duration_days in rows:
        SP.objects.create(
            plan=plan,
            billing_cycle=billing_cycle,
            seat_bundle=seat_bundle,
            amount=amount,
            duration_days=duration_days,
            currency_iso='XOF',
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_profile_sensitive_media_blur_by_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionpricing',
            name='seat_bundle',
            field=models.CharField(
                choices=[('solo', 'Solo'), ('family', 'Family'), ('team', 'Team')],
                default='solo',
                max_length=24,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='subscriptionpricing',
            unique_together=(),
        ),
        migrations.AlterUniqueTogether(
            name='subscriptionpricing',
            unique_together={('plan', 'billing_cycle', 'seat_bundle')},
        ),
        migrations.RunPython(seed_official_pricing, noop_reverse),
    ]
