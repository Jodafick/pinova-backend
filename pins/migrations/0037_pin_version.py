# Champ version sur Pin (ORM + seed). Idempotent si la colonne existe déjà (ex. BDD Render / offline).

from django.db import connection, migrations, models


def _column_exists(table: str, column: str) -> bool:
    vendor = connection.vendor
    with connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                [table, column],
            )
            return cursor.fetchone() is not None
        if vendor == 'sqlite':
            assert table.replace('_', '').isalnum(), table
            cursor.execute(f'PRAGMA table_info({table})')
            rows = cursor.fetchall()
            return any((r[1] if len(r) > 1 else '') == column for r in rows)
    return False


def ensure_pin_version_column(apps, schema_editor):
    Pin = apps.get_model('pins', 'Pin')
    table = Pin._meta.db_table
    q = connection.ops.quote_name
    if not _column_exists(table, 'version'):
        if connection.vendor == 'postgresql':
            schema_editor.execute(
                f'ALTER TABLE {q(table)} ADD COLUMN {q("version")} INTEGER NOT NULL DEFAULT 1'
            )
            schema_editor.execute(
                f'ALTER TABLE {q(table)} ALTER COLUMN {q("version")} DROP DEFAULT'
            )
        elif connection.vendor == 'sqlite':
            schema_editor.execute(
                f'ALTER TABLE {q(table)} ADD COLUMN {q("version")} INTEGER NOT NULL DEFAULT 1'
            )
        else:
            field = models.PositiveIntegerField(default=1)
            field.set_attributes_from_name('version')
            schema_editor.add_field(Pin, field)
        return
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            f'UPDATE {q(table)} SET {q("version")} = 1 WHERE {q("version")} IS NULL'
        )
    elif connection.vendor == 'sqlite':
        schema_editor.execute(
            f'UPDATE {q(table)} SET {q("version")} = 1 WHERE {q("version")} IS NULL'
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0036_pin_updated_at'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='pin',
                    name='version',
                    field=models.PositiveIntegerField(default=1),
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_pin_version_column, noop_reverse),
            ],
        ),
    ]
