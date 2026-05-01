from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('pins', '0011_comment_media'),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('query', models.CharField(max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_interactions', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PinViewEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='view_events', to='pins.pin')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pin_view_events', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
