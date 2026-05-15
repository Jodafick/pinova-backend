from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0002_pin_shares_count_userinteraction_share'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='upload_idempotency_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=128),
        ),
        migrations.AddConstraint(
            model_name='pin',
            constraint=models.UniqueConstraint(
                condition=~models.Q(upload_idempotency_key=''),
                fields=('author', 'upload_idempotency_key'),
                name='unique_pin_upload_idempotency_per_author',
            ),
        ),
    ]
