from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0009_commentlike'),
    ]

    operations = [
        migrations.CreateModel(
            name='TopicTranslation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('topic', models.CharField(max_length=120, unique=True)),
                ('translations', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['topic'],
            },
        ),
    ]
