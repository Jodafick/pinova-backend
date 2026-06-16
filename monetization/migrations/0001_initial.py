import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('fotos', '0004_machinetranslationcache'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoostPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=24, unique=True)),
                ('label', models.CharField(max_length=80)),
                ('duration_hours', models.PositiveIntegerField()),
                ('amount', models.PositiveIntegerField(help_text='Montant en unités mineures (ex. centimes XOF).')),
                ('currency_iso', models.CharField(default='XOF', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['duration_hours'],
            },
        ),
        migrations.CreateModel(
            name='PartnerCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120)),
                ('body', models.CharField(blank=True, default='', max_length=400)),
                ('sponsor_name', models.CharField(blank=True, default='', max_length=80)),
                ('image', models.ImageField(blank=True, null=True, upload_to='partner_ads/')),
                ('cta_label', models.CharField(default='En savoir plus', max_length=40)),
                ('cta_url', models.URLField(max_length=500)),
                ('topic_slug', models.CharField(blank=True, default='', help_text='Optionnel : cibler un topic (slug ou nom). Vide = tous les sujets.', max_length=80)),
                ('country_code', models.CharField(blank=True, default='', max_length=2)),
                ('priority', models.PositiveSmallIntegerField(default=10)),
                ('is_active', models.BooleanField(default=True)),
                ('starts_at', models.DateTimeField(blank=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('impressions', models.PositiveIntegerField(default=0)),
                ('clicks', models.PositiveIntegerField(default=0)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='partner_campaigns_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-priority', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PinBoost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('active', 'Active'), ('expired', 'Expired'), ('canceled', 'Canceled')], default='pending', max_length=16)),
                ('starts_at', models.DateTimeField(blank=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('fedapay_transaction_id', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='foto_boosts', to=settings.AUTH_USER_MODEL)),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='boosts', to='monetization.boostpackage')),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='boosts', to='fotos.pin')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
