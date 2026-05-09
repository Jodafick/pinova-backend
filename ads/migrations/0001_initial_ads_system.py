# Generated manually for Pinova ads — alignée sur ``ads.models`` (Django 6).

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Advertiser',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('legal_name', models.CharField(blank=True, default='', max_length=255)),
                ('tax_id', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('contact_email', models.EmailField(db_index=True, max_length=254)),
                ('website', models.URLField(blank=True, default='')),
                (
                    'status',
                    models.CharField(
                        choices=[('pending', 'Pending'), ('active', 'Active'), ('suspended', 'Suspended')],
                        db_index=True,
                        default='pending',
                        max_length=20,
                    ),
                ),
                ('billing_external_id', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('spam_strike_count', models.PositiveSmallIntegerField(default=0)),
                ('suspended_until', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='AdCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=120, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'parent',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='children',
                        to='ads.adcategory',
                    ),
                ),
            ],
            options={'verbose_name_plural': 'Ad categories', 'ordering': ['slug']},
        ),
        migrations.CreateModel(
            name='BusinessAccount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('display_name', models.CharField(max_length=255)),
                ('timezone', models.CharField(default='UTC', max_length=64)),
                ('currency', models.CharField(default='XOF', max_length=3)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'advertiser',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='business_accounts',
                        to='ads.advertiser',
                    ),
                ),
                (
                    'owner',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='ads_business_accounts',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='Campaign',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                (
                    'objective',
                    models.CharField(
                        choices=[
                            ('awareness', 'Awareness'),
                            ('traffic', 'Traffic'),
                            ('engagement', 'Engagement'),
                            ('app_install', 'App install'),
                        ],
                        db_index=True,
                        default='awareness',
                        max_length=32,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('draft', 'Draft'),
                            ('active', 'Active'),
                            ('paused', 'Paused'),
                            ('archived', 'Archived'),
                        ],
                        db_index=True,
                        default='draft',
                        max_length=20,
                    ),
                ),
                (
                    'bid_strategy',
                    models.CharField(choices=[('cpm', 'CPM'), ('cpc', 'CPC')], default='cpm', max_length=8),
                ),
                (
                    'bid_micro',
                    models.BigIntegerField(
                        default=0,
                        help_text='En micro-unités monétaires (1/1_000_000) pour éviter les flottants.',
                    ),
                ),
                ('start_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('end_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business_account',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='campaigns',
                        to='ads.businessaccount',
                    ),
                ),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CampaignBudget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'budget_type',
                    models.CharField(
                        choices=[('daily', 'Daily'), ('lifetime', 'Lifetime')], default='daily', max_length=16
                    ),
                ),
                ('budget_micro', models.BigIntegerField(default=0)),
                ('spend_micro', models.BigIntegerField(default=0)),
                (
                    'pacing',
                    models.CharField(choices=[('even', 'Even'), ('asap', 'ASAP')], default='even', max_length=16),
                ),
                ('day_cursor', models.DateField(blank=True, db_index=True, null=True)),
                ('spend_micro_day', models.BigIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'campaign',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='budget',
                        to='ads.campaign',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AudienceSegment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('rules', models.JSONField(default=dict, help_text='DSL de ciblage réutilisable.')),
                ('estimated_size', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business_account',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='audience_segments',
                        to='ads.businessaccount',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdCreative',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('headline', models.CharField(blank=True, default='', max_length=255)),
                ('body', models.TextField(blank=True, default='')),
                ('cta_text', models.CharField(blank=True, default='', max_length=64)),
                ('brand_name', models.CharField(blank=True, default='', max_length=128)),
                ('brand_logo_url', models.URLField(blank=True, default='')),
                ('media_image', models.ImageField(blank=True, null=True, upload_to='ads/creatives/')),
                ('media_video_url', models.URLField(blank=True, default='')),
                ('aspect_ratio', models.CharField(blank=True, default='9:16', max_length=16)),
                (
                    'autoplay_muted_default',
                    models.BooleanField(
                        default=True,
                        help_text='Côté client : autoplay silencieux ; son uniquement après interaction.',
                    ),
                ),
                ('duration_seconds_est', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business_account',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_creatives',
                        to='ads.businessaccount',
                    ),
                ),
                ('categories', models.ManyToManyField(blank=True, related_name='creatives', to='ads.adcategory')),
            ],
        ),
        migrations.CreateModel(
            name='Ad',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('draft', 'Draft'),
                            ('active', 'Active'),
                            ('paused', 'Paused'),
                            ('rejected', 'Rejected'),
                        ],
                        db_index=True,
                        default='draft',
                        max_length=20,
                    ),
                ),
                (
                    'ad_format',
                    models.CharField(
                        choices=[
                            ('feed_video', 'Feed video (native)'),
                            ('feed_image', 'Feed image (native)'),
                            ('sidebar_native', 'Sidebar native (web)'),
                            ('explore_native', 'Explore / trending native'),
                        ],
                        db_index=True,
                        default='feed_video',
                        max_length=32,
                    ),
                ),
                ('destination_url', models.URLField(blank=True, default='')),
                ('deep_link', models.CharField(blank=True, default='', max_length=512)),
                (
                    'priority_boost',
                    models.SmallIntegerField(
                        default=0,
                        help_text='Ajustement manuel léger (qualité organique reste prioritaire).',
                        validators=[
                            django.core.validators.MinValueValidator(-50),
                            django.core.validators.MaxValueValidator(50),
                        ],
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'campaign',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ads', to='ads.campaign'),
                ),
                (
                    'creative',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='ads',
                        to='ads.adcreative',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdTargeting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('age_min', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('age_max', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('genders', models.JSONField(blank=True, default=list)),
                ('countries', models.JSONField(blank=True, default=list)),
                (
                    'cities',
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text='Liste normalisée: label, country_code, lat, lng, provider_place_id',
                    ),
                ),
                ('languages', models.JSONField(blank=True, default=list)),
                ('devices', models.JSONField(blank=True, default=list)),
                ('operating_systems', models.JSONField(blank=True, default=list)),
                ('interest_topic_slugs', models.JSONField(blank=True, default=list)),
                ('interest_category_slugs', models.JSONField(blank=True, default=list)),
                ('behavior_min_watch_7d_sec', models.PositiveIntegerField(blank=True, null=True)),
                ('behavior_min_engagement_rate', models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ('recency_active_within_hours', models.PositiveIntegerField(blank=True, null=True)),
                ('include_hashtags', models.JSONField(blank=True, default=list)),
                ('exclude_hashtags', models.JSONField(blank=True, default=list)),
                ('search_keywords', models.JSONField(blank=True, default=list)),
                (
                    'raw_rules',
                    models.JSONField(blank=True, default=dict, help_text='Extensions / règles additionnelles.'),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'ad',
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='targeting', to='ads.ad'),
                ),
                (
                    'audience_segments',
                    models.ManyToManyField(blank=True, related_name='targeted_ads', to='ads.audiencesegment'),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdImpression',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('placement', models.CharField(choices=[('feed_mobile', 'Feed mobile'), ('feed_web', 'Feed web'), ('sidebar_web', 'Sidebar desktop web'), ('explore', 'Explore / trending')], db_index=True, max_length=24)),
                ('served_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('is_valid', models.BooleanField(db_index=True, default=True)),
                (
                    'client_context',
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='app_version, surface, viewport, connection_type, etc.',
                    ),
                ),
                ('device_fingerprint_hash', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('ip_hash', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('fraud_flags', models.JSONField(blank=True, default=list)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                (
                    'ad',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='impressions', to='ads.ad'),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='ad_impressions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdClick',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('clicked_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('click_x', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('click_y', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('referrer', models.CharField(blank=True, default='', max_length=512)),
                ('is_suspicious', models.BooleanField(db_index=True, default=False)),
                ('suspicion_reasons', models.JSONField(blank=True, default=list)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                (
                    'ad',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clicks', to='ads.ad'),
                ),
                (
                    'impression',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='clicks',
                        to='ads.adimpression',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='ad_clicks',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdView',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField(db_index=True)),
                ('duration_ms', models.PositiveIntegerField(default=0)),
                (
                    'visible_pct_max',
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[django.core.validators.MaxValueValidator(100)],
                    ),
                ),
                ('completed', models.BooleanField(db_index=True, default=False)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                (
                    'ad',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='views', to='ads.ad'),
                ),
                (
                    'impression',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='views',
                        to='ads.adimpression',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='ad_views',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdWatchSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField(db_index=True)),
                ('ended_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('total_watched_ms', models.PositiveIntegerField(default=0)),
                (
                    'milestones',
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='p25, p50, p75, p100 timestamps ou compteurs.',
                    ),
                ),
                ('heartbeat_count', models.PositiveIntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                (
                    'ad',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='watch_sessions',
                        to='ads.ad',
                    ),
                ),
                (
                    'ad_view',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='watch_sessions',
                        to='ads.adview',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='ad_watch_sessions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.CharField(db_index=True, max_length=64)),
                ('details', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'ad',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='ads.ad'),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_reports',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdHide',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'ad',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hides', to='ads.ad'),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_hides',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdFrequencyTracking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('impressions_1h', models.PositiveSmallIntegerField(default=0)),
                ('impressions_24h', models.PositiveIntegerField(default=0)),
                ('impressions_7d', models.PositiveIntegerField(default=0)),
                ('last_shown_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('rotation_bucket', models.PositiveSmallIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'ad',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='frequency_tracking',
                        to='ads.ad',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_frequency_tracking',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='UserInterestScore',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    'key_type',
                    models.CharField(
                        choices=[
                            ('topic', 'Topic'),
                            ('hashtag', 'Hashtag'),
                            ('category', 'Category'),
                            ('search', 'Search'),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ('key_slug', models.CharField(db_index=True, max_length=190)),
                ('score', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('raw_score', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('source_counts', models.JSONField(blank=True, default=dict)),
                ('last_signal_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_interest_scores',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='UserBehaviorProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_watch_seconds_7d', models.PositiveIntegerField(default=0)),
                ('total_watch_seconds_30d', models.PositiveIntegerField(default=0)),
                ('engagement_rate_30d', models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ('category_histogram', models.JSONField(blank=True, default=dict)),
                ('hashtag_histogram', models.JSONField(blank=True, default=dict)),
                ('search_histogram', models.JSONField(blank=True, default=dict)),
                ('device_primary', models.CharField(blank=True, default='', max_length=32)),
                ('os_primary', models.CharField(blank=True, default='', max_length=32)),
                ('last_active_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('ads_hidden_30d', models.PositiveIntegerField(default=0)),
                ('ads_reported_30d', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_behavior_profile',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='UserTrustScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trust', models.DecimalField(decimal_places=4, default=0.75, max_digits=5)),
                ('click_velocity_score', models.DecimalField(decimal_places=4, default=1, max_digits=5)),
                ('impression_anomaly_score', models.DecimalField(decimal_places=4, default=1, max_digits=5)),
                ('automation_flags', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='ad_trust_score',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdQualityScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quality_0_100', models.PositiveSmallIntegerField(default=72)),
                ('hide_rate', models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ('report_rate', models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ('ctr_smoothed', models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ('engagement_bonus', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('watch_bonus', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('penalty_hidden', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('penalty_reported', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'ad',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='quality',
                        to='ads.ad',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdDeliveryLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_id', models.UUIDField(db_index=True)),
                ('placement', models.CharField(choices=[('feed_mobile', 'Feed mobile'), ('feed_web', 'Feed web'), ('sidebar_web', 'Sidebar desktop web'), ('explore', 'Explore / trending')], db_index=True, max_length=24)),
                ('candidates', models.JSONField(blank=True, default=list)),
                ('scores', models.JSONField(blank=True, default=dict)),
                ('reason', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'chosen_ad',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='delivery_logs',
                        to='ads.ad',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='ad_delivery_logs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdPerformanceSnapshot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('period_start', models.DateTimeField(db_index=True)),
                ('period_end', models.DateTimeField(db_index=True)),
                (
                    'granularity',
                    models.CharField(choices=[('hour', 'Hour'), ('day', 'Day')], db_index=True, max_length=8),
                ),
                ('impressions', models.PositiveIntegerField(default=0)),
                ('valid_impressions', models.PositiveIntegerField(default=0)),
                ('clicks', models.PositiveIntegerField(default=0)),
                ('views', models.PositiveIntegerField(default=0)),
                ('completes', models.PositiveIntegerField(default=0)),
                ('spend_micro', models.BigIntegerField(default=0)),
                ('watch_duration_ms_total', models.BigIntegerField(default=0)),
                ('watch_duration_ms_avg', models.BigIntegerField(default=0)),
                ('engagement_events', models.PositiveIntegerField(default=0)),
                ('hidden_count', models.PositiveIntegerField(default=0)),
                ('reported_count', models.PositiveIntegerField(default=0)),
                ('ctr', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('cpm_micro', models.BigIntegerField(default=0)),
                ('cpc_micro', models.BigIntegerField(default=0)),
                ('engagement_rate', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('retention_proxy', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('computed_at', models.DateTimeField(auto_now_add=True)),
                (
                    'ad',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='performance_snapshots',
                        to='ads.ad',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='AdPendingEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'event_type',
                    models.CharField(
                        choices=[
                            ('impression', 'Impression'),
                            ('click', 'Click'),
                            ('view', 'View'),
                            ('watch', 'Watch'),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                ('payload', models.JSONField(default=dict)),
                ('dedupe_key', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('processed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('last_error', models.TextField(blank=True, default='')),
            ],
        ),
        migrations.AddIndex(model_name='advertiser', index=models.Index(fields=['status', 'created_at'], name='ads_adv_stat_crt_idx')),
        migrations.AddConstraint(
            model_name='businessaccount',
            constraint=models.UniqueConstraint(fields=('owner', 'advertiser'), name='ads_business_owner_adv_uniq'),
        ),
        migrations.AddIndex(model_name='businessaccount', index=models.Index(fields=['advertiser', 'is_active'], name='ads_biz_adv_act_idx')),
        migrations.AddIndex(model_name='campaign', index=models.Index(fields=['business_account', 'status'], name='ads_camp_ba_stat_idx')),
        migrations.AddIndex(model_name='campaign', index=models.Index(fields=['status', 'start_at', 'end_at'], name='ads_camp_win_idx')),
        migrations.AddIndex(model_name='campaignbudget', index=models.Index(fields=['day_cursor'], name='ads_cbudget_day_idx')),
        migrations.AddIndex(model_name='audiencesegment', index=models.Index(fields=['business_account', 'name'], name='ads_seg_ba_name_idx')),
        migrations.AddIndex(model_name='adcreative', index=models.Index(fields=['business_account', '-created_at'], name='ads_cr_ba_crt_idx')),
        migrations.AddIndex(model_name='ad', index=models.Index(fields=['campaign', 'status'], name='ads_ad_camp_stat_idx')),
        migrations.AddIndex(model_name='ad', index=models.Index(fields=['status', 'ad_format'], name='ads_ad_stat_fmt_idx')),
        migrations.AddIndex(model_name='adtargeting', index=models.Index(fields=['age_min', 'age_max'], name='ads_tgt_age_idx')),
        migrations.AddIndex(model_name='adimpression', index=models.Index(fields=['ad', 'served_at'], name='ads_imp_ad_time_idx')),
        migrations.AddIndex(model_name='adimpression', index=models.Index(fields=['user', 'served_at'], name='ads_imp_user_time_idx')),
        migrations.AddIndex(model_name='adimpression', index=models.Index(fields=['placement', 'served_at'], name='ads_imp_pl_time_idx')),
        migrations.AddIndex(model_name='adimpression', index=models.Index(fields=['request_id'], name='ads_imp_req_idx')),
        migrations.AddIndex(model_name='adclick', index=models.Index(fields=['ad', 'clicked_at'], name='ads_clk_ad_time_idx')),
        migrations.AddIndex(model_name='adclick', index=models.Index(fields=['user', 'clicked_at'], name='ads_clk_user_time_idx')),
        migrations.AddIndex(model_name='adview', index=models.Index(fields=['ad', 'started_at'], name='ads_view_ad_time_idx')),
        migrations.AddIndex(model_name='adview', index=models.Index(fields=['user', 'started_at'], name='ads_view_user_time_idx')),
        migrations.AddIndex(model_name='adwatchsession', index=models.Index(fields=['ad', 'started_at'], name='ads_ws_ad_start_idx')),
        migrations.AddIndex(model_name='adwatchsession', index=models.Index(fields=['user', 'started_at'], name='ads_ws_user_start_idx')),
        migrations.AddIndex(model_name='adreport', index=models.Index(fields=['ad', 'created_at'], name='ads_rep_ad_crt_idx')),
        migrations.AddConstraint(
            model_name='adhide',
            constraint=models.UniqueConstraint(fields=('user', 'ad'), name='ads_hide_user_ad_uniq'),
        ),
        migrations.AddIndex(model_name='adhide', index=models.Index(fields=['ad', '-created_at'], name='ads_hide_ad_crt_idx')),
        migrations.AddConstraint(
            model_name='adfrequencytracking',
            constraint=models.UniqueConstraint(fields=('user', 'ad'), name='ads_freq_user_ad_uniq'),
        ),
        migrations.AddIndex(model_name='adfrequencytracking', index=models.Index(fields=['user', 'last_shown_at'], name='ads_freq_user_last_idx')),
        migrations.AddConstraint(
            model_name='userinterestscore',
            constraint=models.UniqueConstraint(fields=('user', 'key_type', 'key_slug'), name='ads_interest_user_key_uniq'),
        ),
        migrations.AddIndex(model_name='userinterestscore', index=models.Index(fields=['user', 'key_type', 'score'], name='ads_int_user_type_sc_idx')),
        migrations.AddIndex(model_name='userbehaviorprofile', index=models.Index(fields=['-last_active_at'], name='ads_ubp_last_act_idx')),
        migrations.AddIndex(model_name='adqualityscore', index=models.Index(fields=['-quality_0_100'], name='ads_qual_score_idx')),
        migrations.AddIndex(model_name='addeliverylog', index=models.Index(fields=['placement', 'created_at'], name='ads_dlog_pl_crt_idx')),
        migrations.AddConstraint(
            model_name='adperformancesnapshot',
            constraint=models.UniqueConstraint(
                fields=('ad', 'period_start', 'granularity'),
                name='ads_perf_ad_period_gran_uniq',
            ),
        ),
        migrations.AddIndex(
            model_name='adperformancesnapshot',
            index=models.Index(fields=['ad', 'granularity', 'period_start'], name='ads_perf_ad_gran_ps_idx'),
        ),
        migrations.AddIndex(model_name='adpendingevent', index=models.Index(fields=['processed_at', 'created_at'], name='ads_pend_proc_crt_idx')),
        migrations.AddIndex(model_name='adpendingevent', index=models.Index(fields=['event_type', 'processed_at'], name='ads_pend_type_proc_idx')),
    ]
