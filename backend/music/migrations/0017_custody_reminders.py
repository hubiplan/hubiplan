import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0016_engagement_documents"),
        ("todos", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="MusicReminderPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("enabled", models.BooleanField(default=False)),
                ("days_ahead", models.PositiveSmallIntegerField(default=7)),
                ("scores", models.BooleanField(default=True)),
                ("equipment", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["organization", "user"], name="music_reminder_preference_once"
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="MusicReminderTask",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("kind", models.CharField(max_length=16)),
                ("source", models.PositiveBigIntegerField()),
                ("deadline", models.DateField()),
                ("managed_version", models.PositiveIntegerField(default=1)),
                ("auto_closed", models.BooleanField(default=False)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "preference",
                    models.ForeignKey(
                        "music.musicreminderpreference",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                    ),
                ),
                (
                    "todo",
                    models.OneToOneField(
                        "todos.todo",
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["preference", "kind", "source", "deadline"],
                        name="music_reminder_source_once",
                    )
                ]
            },
        ),
        *[
            migrations.RunSQL(enable_rls_sql(table), disable_rls_sql(table))
            for table in ["music_musicreminderpreference", "music_musicremindertask"]
        ],
    ]
