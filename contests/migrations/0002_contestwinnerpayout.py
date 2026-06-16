# Generated manually for ContestWinnerPayout

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contests', '0001_initial'),
        ('fotos', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ContestWinnerPayout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('fotos', 'Pins'), ('referral', 'Referral')], db_index=True, max_length=16)),
                ('winner_rank', models.PositiveSmallIntegerField()),
                ('gross_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('currency', models.CharField(default='EUR', max_length=8)),
                (
                    'payment_status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('paid', 'Paid'),
                            ('failed', 'Failed'),
                            ('withheld', 'Withheld'),
                        ],
                        db_index=True,
                        default='pending',
                        max_length=16,
                    ),
                ),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('payment_reference', models.CharField(blank=True, default='', max_length=191)),
                ('notes', models.TextField(blank=True, default='')),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'beneficiary',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'contest',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='winner_payouts', to='contests.contestsettings'),
                ),
                (
                    'pin',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to='fotos.pin',
                    ),
                ),
            ],
            options={
                'ordering': ['contest_id', 'source', 'winner_rank'],
            },
        ),
        migrations.AddIndex(
            model_name='contestwinnerpayout',
            index=models.Index(fields=['contest', 'source', 'payment_status'], name='contests_con_contest_efb6e4_idx'),
        ),
        migrations.AddConstraint(
            model_name='contestwinnerpayout',
            constraint=models.UniqueConstraint(fields=('contest', 'source', 'winner_rank'), name='contest_winpayout_unique_contest_source_rank'),
        ),
    ]
