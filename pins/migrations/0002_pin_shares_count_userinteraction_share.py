from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pin',
            name='shares_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='userinteraction',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('view', 'View'),
                    ('like', 'Like'),
                    ('click', 'Click'),
                    ('save', 'Save'),
                    ('share', 'Share'),
                    ('creator_visit', 'Creator Visit'),
                ],
                max_length=20,
            ),
        ),
    ]
