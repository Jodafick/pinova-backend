# Generated manually for Pinova profile & onboarding extension

from django.db import migrations, models
from django.utils import timezone


def mark_existing_profiles_onboarded(apps, schema_editor):
    Profile = apps.get_model('accounts', 'Profile')
    now = timezone.now()
    Profile.objects.filter(onboarding_completed_at__isnull=True).update(onboarding_completed_at=now)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_mobileoauthlogincode_mobile_state_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='first_name',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='profile',
            name='last_name',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='profile',
            name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='covers/'),
        ),
        migrations.AddField(
            model_name='profile',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Prefer not to say'),
                    ('woman', 'Woman'),
                    ('man', 'Man'),
                    ('non_binary', 'Non-binary'),
                    ('other', 'Other'),
                ],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='pronouns',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='profile',
            name='city',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='profile',
            name='website',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='profile',
            name='job_title',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='profile',
            name='school',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='profile',
            name='company',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='profile',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='profile',
            name='interests',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='profile',
            name='followed_onboarding_creators',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='profile',
            name='theme_mode',
            field=models.CharField(
                choices=[('light', 'Light'), ('dark', 'Dark'), ('system', 'System')],
                default='system',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='accent_color',
            field=models.CharField(default='rose', max_length=24),
        ),
        migrations.AddField(
            model_name='profile',
            name='date_format',
            field=models.CharField(default='auto', max_length=24),
        ),
        migrations.AddField(
            model_name='profile',
            name='timezone',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='profile',
            name='presence_status',
            field=models.CharField(
                choices=[
                    ('available', 'Available'),
                    ('busy', 'Busy'),
                    ('invisible', 'Invisible'),
                ],
                default='available',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='show_activity',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='show_last_seen',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='allow_dm',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='allow_tags_mentions',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='favorite_quote',
            field=models.CharField(blank=True, default='', max_length=280),
        ),
        migrations.AddField(
            model_name='profile',
            name='hobbies',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='profile',
            name='skills',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='profile',
            name='social_links',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='profile',
            name='onboarding_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_profiles_onboarded, migrations.RunPython.noop),
    ]
