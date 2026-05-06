from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pins", "0032_ai_recommendation_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddField(
            model_name="comment",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="pin",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddField(
            model_name="pin",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="ProcessedAction",
            fields=[
                ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("client_id", models.CharField(db_index=True, max_length=100)),
                ("action_type", models.CharField(max_length=40)),
                ("processed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-processed_at"],
                "indexes": [
                    models.Index(fields=["user", "-processed_at"], name="pins_proces_user_id_d46ce5_idx"),
                    models.Index(fields=["client_id", "-processed_at"], name="pins_proces_client__f77315_idx"),
                ],
            },
        ),
    ]
