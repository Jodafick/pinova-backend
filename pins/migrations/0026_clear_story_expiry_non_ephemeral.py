# Generated manually — nettoie story_expires_at pour les pins « story » classiques
# (is_story sans story_ephemeral) : seules les stories standalone éphémères portent une expiry.

from django.db import migrations


def clear_expiry_on_non_ephemeral_stories(apps, schema_editor):
    Pin = apps.get_model('pins', 'Pin')
    Pin.objects.filter(is_story=True, story_ephemeral=False).update(story_expires_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ('pins', '0025_pin_story_ephemeral'),
    ]

    operations = [
        migrations.RunPython(clear_expiry_on_non_ephemeral_stories, migrations.RunPython.noop),
    ]
