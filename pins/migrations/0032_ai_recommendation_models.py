from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("pins", "0031_faqitem"),
    ]

    operations = [
        migrations.CreateModel(
            name="PinEmbedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("embedding", models.JSONField(blank=True, default=list)),
                ("embedding_dim", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pin",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embedding_profile",
                        to="pins.pin",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="UserEmbedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("embedding", models.JSONField(blank=True, default=list)),
                ("embedding_dim", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embedding_profile",
                        to="auth.user",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="UserInteraction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("view", "View"),
                            ("like", "Like"),
                            ("click", "Click"),
                            ("save", "Save"),
                            ("creator_visit", "Creator Visit"),
                        ],
                        max_length=20,
                    ),
                ),
                ("dwell_seconds", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "creator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="creator_interactions",
                        to="auth.user",
                    ),
                ),
                (
                    "pin",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_interactions",
                        to="pins.pin",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pin_interactions",
                        to="auth.user",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TagInvisible",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tag", models.CharField(max_length=100)),
                ("confidence", models.FloatField(default=0.0)),
                ("source", models.CharField(default="auto", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pin",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invisible_tags",
                        to="pins.pin",
                    ),
                ),
            ],
            options={"ordering": ["-confidence", "tag"], "unique_together": {("pin", "tag")}},
        ),
        migrations.AddIndex(
            model_name="userinteraction",
            index=models.Index(fields=["user", "-created_at"], name="pins_userin_user_id_370fa2_idx"),
        ),
        migrations.AddIndex(
            model_name="userinteraction",
            index=models.Index(fields=["event_type", "-created_at"], name="pins_userin_event_t_22a484_idx"),
        ),
    ]
