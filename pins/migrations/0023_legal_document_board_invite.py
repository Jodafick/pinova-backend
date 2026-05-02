# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pins', '0022_pin_media_sensitive_blur'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.CharField(choices=[('privacy', 'Politique de confidentialité'), ('terms', "Conditions d'utilisation")], max_length=40, unique=True)),
                ('body_fr', models.TextField(blank=True, default='')),
                ('body_en', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['slug'],
            },
        ),
        migrations.CreateModel(
            name='BoardCollaborationInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('board', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collaboration_invites', to='pins.board')),
                ('invited_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='board_collab_invites_sent', to=settings.AUTH_USER_MODEL)),
                ('invitee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='board_collab_invites_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='boardcollaborationinvite',
            constraint=models.UniqueConstraint(fields=('board', 'invitee'), name='unique_board_collab_invitee'),
        ),
    ]
