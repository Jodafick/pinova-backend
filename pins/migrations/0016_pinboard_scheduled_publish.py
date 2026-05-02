from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_board_links(apps, schema_editor):
    PinBoard = apps.get_model('pins', 'PinBoard')
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT pin_id, board_id FROM pins_pin_boards')
        rows = cursor.fetchall()
    for pin_id, board_id in rows:
        PinBoard.objects.get_or_create(
            pin_id=pin_id,
            board_id=board_id,
            defaults={'position': 0},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0015_pin_link'),
    ]

    operations = [
        migrations.CreateModel(
            name='PinBoard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(default=0)),
                (
                    'board',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pin_board_memberships',
                        to='pins.board',
                    ),
                ),
                (
                    'pin',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pin_board_memberships',
                        to='pins.pin',
                    ),
                ),
            ],
            options={
                'ordering': ['position', 'id'],
                'unique_together': {('pin', 'board')},
            },
        ),
        migrations.RunPython(copy_legacy_board_links, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='pin',
            name='boards',
        ),
        migrations.AddField(
            model_name='pin',
            name='boards',
            field=models.ManyToManyField(blank=True, related_name='pins', through='pins.PinBoard', to='pins.board'),
        ),
        migrations.AddField(
            model_name='pin',
            name='scheduled_publish_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['scheduled_publish_at'], name='pins_pin_sched_pub_idx'),
        ),
    ]
