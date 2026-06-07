"""Index GIN pg_trgm — pins.title, hashtags, author username, boards, profils."""

from django.db import migrations


FORWARD_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS pins_pin_title_trgm_gin
    ON pins_pin USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS pins_pin_description_trgm_gin
    ON pins_pin USING gin (description gin_trgm_ops);

CREATE INDEX IF NOT EXISTS pins_hashtag_name_trgm_gin
    ON pins_hashtag USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS pins_board_name_trgm_gin
    ON pins_board USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS pins_board_description_trgm_gin
    ON pins_board USING gin (description gin_trgm_ops);

CREATE INDEX IF NOT EXISTS auth_user_username_trgm_gin
    ON auth_user USING gin (username gin_trgm_ops);

CREATE INDEX IF NOT EXISTS accounts_profile_display_name_trgm_gin
    ON accounts_profile USING gin (display_name gin_trgm_ops);
"""

REVERSE_SQL = """
DROP INDEX IF EXISTS pins_pin_title_trgm_gin;
DROP INDEX IF EXISTS pins_pin_description_trgm_gin;
DROP INDEX IF EXISTS pins_hashtag_name_trgm_gin;
DROP INDEX IF EXISTS pins_board_name_trgm_gin;
DROP INDEX IF EXISTS pins_board_description_trgm_gin;
DROP INDEX IF EXISTS auth_user_username_trgm_gin;
DROP INDEX IF EXISTS accounts_profile_display_name_trgm_gin;
"""


def apply_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(FORWARD_SQL)


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0006_pin_feed_indexes'),
        ('accounts', '0009_profile_retention_prefs'),
    ]

    operations = [
        migrations.RunPython(apply_trigram_indexes, drop_trigram_indexes),
    ]
