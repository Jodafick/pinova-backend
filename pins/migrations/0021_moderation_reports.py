# Generated manually — modération / signalements

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pins', '0020_pin_comments_policy_comment_hidden'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='needs_review',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='pin',
            name='report_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pin',
            name='moderation_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='comment',
            name='needs_review',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='comment',
            name='report_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='comment',
            name='moderation_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='ContentReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('comment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='pins.comment')),
                ('pin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='pins.pin')),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='contentreport',
            index=models.Index(fields=['pin', '-created_at'], name='pins_conten_pin_id_a83658_idx'),
        ),
        migrations.AddIndex(
            model_name='contentreport',
            index=models.Index(fields=['comment', '-created_at'], name='pins_conten_comment_e83eab_idx'),
        ),
    ]
