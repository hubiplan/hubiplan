# Dateien in die Nextcloud ablegen (mit Frist je Art) und aus ihr übernehmen

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


def _char(name, verbose, default, max_length=64):
    return migrations.AddField(
        model_name="client",
        name=name,
        field=models.CharField(
            blank=True,
            default=default,
            db_default=default,
            max_length=max_length,
            verbose_name=verbose,
        ),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0009_gruppen_abgleich"),
        ("organizations", "0045_hilfe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="files_enabled",
            field=models.BooleanField(
                default=False, db_default=False, verbose_name="In Nextcloud ablegen"
            ),
        ),
        _char("files_root", "Ordner im Dienstkonto", "HUBIplan", 100),
        _char("files_board_group", "Gruppe für „Vorstand“", "Vorstand"),
        _char("files_finance_group", "Gruppe für „Kasse“", "Kassierer"),
        _char("files_members_group", "Gruppe für „Mitglieder“", "Mitglieder"),
        migrations.AddField(
            model_name="client",
            name="files_retention",
            field=models.JSONField(
                blank=True, db_default={}, default=dict, verbose_name="Fristen je Art"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="files_shares",
            field=models.JSONField(blank=True, db_default={}, default=dict),
        ),
        _char("files_source", "Ordner zum Übernehmen", "", 300),
        _char("files_error", None, "", 500),
        migrations.CreateModel(
            name="FileItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "target",
                    models.CharField(
                        choices=[
                            ("board", "Vorstand"),
                            ("finance", "Kasse"),
                            ("members", "Mitglieder"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("records", "Beschlüsse und Grundlagen"),
                            ("finance", "Kassen- und Steuerunterlagen"),
                            ("statistics", "Planung und Statistik ohne Personen"),
                            ("reports", "Meldungen an Verbände"),
                            ("personal", "Personenbezogene Listen"),
                            ("other", "Sonstiges"),
                        ],
                        max_length=12,
                    ),
                ),
                ("path", models.CharField(max_length=400)),
                ("size", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delete_after", models.DateField(blank=True, null=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="file_items",
                        to="oidc.client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Datei in der Nextcloud",
                "verbose_name_plural": "Dateien in der Nextcloud",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunSQL(enable_rls_sql("oidc_fileitem"), disable_rls_sql("oidc_fileitem")),
    ]
