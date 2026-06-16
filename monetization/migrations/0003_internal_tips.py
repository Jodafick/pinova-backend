import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('fotos', '0004_machinetranslationcache'),
        ('monetization', '0002_seed_boost_packages'),
    ]

    operations = [
        migrations.CreateModel(
            name='TipPlatformConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('commission_percent', models.PositiveSmallIntegerField(default=10, help_text='Part prélevée par Fotoce sur chaque pourboire (ex. 10 = 10 %).')),
                ('min_tip_amount', models.PositiveIntegerField(default=500)),
                ('max_tip_amount', models.PositiveIntegerField(default=500000)),
                ('min_withdrawal_amount', models.PositiveIntegerField(default=5000)),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Tip platform config',
            },
        ),
        migrations.CreateModel(
            name='CreatorWallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balance_available', models.PositiveIntegerField(default=0)),
                ('balance_reserved', models.PositiveIntegerField(default=0)),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('total_received_gross', models.PositiveBigIntegerField(default=0)),
                ('total_received_net', models.PositiveBigIntegerField(default=0)),
                ('total_withdrawn', models.PositiveBigIntegerField(default=0)),
                ('payout_phone', models.CharField(blank=True, default='', max_length=32)),
                ('payout_label', models.CharField(blank=True, default='', max_length=80)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='creator_wallet', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Creator wallet',
            },
        ),
        migrations.CreateModel(
            name='TipWithdrawal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.PositiveIntegerField()),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('payout_phone', models.CharField(max_length=32)),
                ('payout_label', models.CharField(blank=True, default='', max_length=80)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('paid', 'Paid')], default='pending', max_length=16)),
                ('admin_note', models.CharField(blank=True, default='', max_length=400)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tip_withdrawals', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TipTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_gross', models.PositiveIntegerField()),
                ('commission_amount', models.PositiveIntegerField()),
                ('amount_net', models.PositiveIntegerField()),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('message', models.CharField(blank=True, default='', max_length=280)),
                ('fedapay_transaction_id', models.CharField(max_length=64, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('failed', 'Failed'), ('canceled', 'Canceled')], default='pending', max_length=16)),
                ('fedapay_payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('donor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tips_sent', to=settings.AUTH_USER_MODEL)),
                ('pin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tips', to='fotos.pin')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tips_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('monetization', 'TipPlatformConfig').objects.get_or_create(pk=1),
            migrations.RunPython.noop,
        ),
    ]
