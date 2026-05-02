# Generated manually for famille / petite équipe (sièges + invitations).

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0016_profile_account_scheduled_deletion'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='subscription_seat_bundle',
            field=models.CharField(blank=True, default='solo', max_length=24),
        ),
        migrations.AddField(
            model_name='profile',
            name='subscription_sponsor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='provisioned_subscription_seats',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='SubscriptionSeatInvitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token_hash', models.CharField(editable=False, max_length=64)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('accepted', 'accepted'), ('declined', 'declined'), ('expired', 'expired'), ('revoked', 'revoked')], default='pending', max_length=20)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('invitee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seat_invitations_received', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seat_invitations_sent', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['owner', 'status'], name='accounts_su_owner_i_61e4e4_idx'),
                    models.Index(fields=['invitee', 'status'], name='accounts_su_invitee_4d7d5c_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='SubscriptionSeatMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seat_memberships_received', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seat_memberships_owned', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['owner'], name='accounts_su_owner_i_82c3b2_idx'),
                    models.Index(fields=['member'], name='accounts_su_member__b5e8fb_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('owner', 'member'), name='uniq_subscription_seat_owner_member'),
                    models.UniqueConstraint(fields=('member',), name='uniq_subscription_seat_member_singleton'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='subscriptionseatinvitation',
            constraint=models.UniqueConstraint(
                condition=models.Q(status='pending'),
                fields=('owner', 'invitee'),
                name='uniq_pending_seat_invite_owner_invitee',
            ),
        ),
    ]
