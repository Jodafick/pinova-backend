# Alignement ORM / BDD : updated_at sur Comment (colonne parfois déjà présente en prod).

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


def add_comment_updated_at_if_missing(apps, schema_editor):
    Comment = apps.get_model('pins', 'Comment')
    table = Comment._meta.db_table
    if _column_exists(table, 'updated_at'):
        return
    quoted = connection.ops.quote_name
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            f'ALTER TABLE {quoted(table)} ADD COLUMN {quoted("updated_at")} '
            f'TIMESTAMPTZ NOT NULL DEFAULT NOW()'
        )
        schema_editor.execute(
            f'ALTER TABLE {quoted(table)} ALTER COLUMN {quoted("updated_at")} DROP DEFAULT'
        )
    elif connection.vendor == 'sqlite':
        schema_editor.execute(
            f'ALTER TABLE {quoted(table)} ADD COLUMN {quoted("updated_at")} '
            f"datetime NOT NULL DEFAULT (datetime('now'))"
        )
    else:
        field = models.DateTimeField(auto_now=True)
        field.set_attributes_from_name('updated_at')
        schema_editor.add_field(Comment, field)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0037_pin_version'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='comment',
                    name='updated_at',
                    field=models.DateTimeField(auto_now=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_comment_updated_at_if_missing, noop_reverse),
            ],
        ),
    ]
