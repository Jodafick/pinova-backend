# Generated migration for pins.MachineTranslationCache

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0003_pin_upload_idempotency_key'),
    ]

    operations = [
        migrations.CreateModel(
            name='MachineTranslationCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_lang', models.CharField(db_index=True, max_length=24)),
                ('target_lang', models.CharField(db_index=True, max_length=24)),
                ('text_sha256', models.CharField(db_index=True, max_length=64)),
                ('source_text', models.TextField()),
                ('translated_text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('hits', models.PositiveBigIntegerField(default=0)),
            ],
            options={
                'ordering': ('-hits', '-id'),
            },
        ),
        migrations.AddConstraint(
            model_name='machinetranslationcache',
            constraint=models.UniqueConstraint(
                fields=('source_lang', 'target_lang', 'text_sha256'),
                name='uniq_mt_cache_lang_hash',
            ),
        ),
    ]
