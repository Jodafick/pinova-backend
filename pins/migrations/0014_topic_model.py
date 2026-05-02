from django.db import migrations, models
from django.utils.text import slugify


def _unique_slug(topic_model, base_name):
    base = slugify(base_name)[:120] or 'topic'
    slug = base
    index = 1
    while topic_model.objects.filter(slug=slug).exists():
        slug = f"{base}-{index}"
        index += 1
    return slug


def forward_migrate_topics(apps, schema_editor):
    Pin = apps.get_model('pins', 'Pin')
    Topic = apps.get_model('pins', 'Topic')

    topic_map = {}
    distinct_names = (
        Pin.objects.exclude(topic__isnull=True)
        .exclude(topic__exact='')
        .values_list('topic', flat=True)
        .distinct()
    )
    for name in distinct_names:
        topic_obj = Topic.objects.create(
            name=name,
            slug=_unique_slug(Topic, name),
            color='#6B7280',
            icon='category',
            is_active=True,
        )
        topic_map[name] = topic_obj.id

    for pin in Pin.objects.all().iterator():
        old_name = (pin.topic or '').strip()
        pin.topic_ref_id = topic_map.get(old_name)
        pin.save(update_fields=['topic_ref'])


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0013_board_collaborators'),
    ]

    operations = [
        migrations.CreateModel(
            name='Topic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=140, unique=True)),
                ('color', models.CharField(default='#6B7280', max_length=80)),
                ('icon', models.CharField(default='category', max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='pin',
            name='topic_ref',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='pins', to='pins.topic'),
        ),
        migrations.RunPython(forward_migrate_topics, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='pin',
            name='topic',
        ),
        migrations.RenameField(
            model_name='pin',
            old_name='topic_ref',
            new_name='topic',
        ),
    ]
