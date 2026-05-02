import django.core.validators
from django.db import migrations, models


def seed_default_subscription_config(apps, schema_editor):
    Config = apps.get_model('accounts', 'PinovaSubscriptionConfig')
    Config.objects.get_or_create(pk=1, defaults={'annual_discount_percent': 10})


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0019_subscriptionpricing_seat_bundle'),
    ]

    operations = [
        migrations.CreateModel(
            name='PinovaSubscriptionConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'annual_discount_percent',
                    models.PositiveSmallIntegerField(
                        default=10,
                        help_text=(
                            'Badge −X % « annuel » sur la page Premium et valeur API annual_discount_percent. '
                            'Mettre 0 pour masquer le badge ; les paiements suivent encore les lignes SubscriptionPricing.'
                        ),
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(99),
                        ],
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuration abonnement Pinova',
                'verbose_name_plural': 'Configuration abonnement Pinova',
            },
        ),
        migrations.RunPython(seed_default_subscription_config, noop_reverse),
    ]
