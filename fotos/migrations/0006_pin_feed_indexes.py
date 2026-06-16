from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fotos', '0005_report_categories_three_branches'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['-created_at'], name='pins_foto_created_desc_idx'),
        ),
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['author', '-created_at'], name='pins_foto_author_created_idx'),
        ),
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['topic', '-created_at'], name='pins_foto_topic_created_idx'),
        ),
    ]
