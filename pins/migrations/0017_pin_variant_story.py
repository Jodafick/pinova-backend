# Generated manually for Pin variants, story 24h fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0016_pinboard_scheduled_publish'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='is_story',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='pin',
            name='story_expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name='PinVariant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('story', 'Story'), ('square', 'Square'), ('landscape', 'Landscape')], max_length=20)),
                ('image', models.ImageField(upload_to='pins/variants/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variant_assets', to='pins.pin')),
            ],
            options={
                'ordering': ['kind'],
                'unique_together': {('pin', 'kind')},
            },
        ),
    ]
