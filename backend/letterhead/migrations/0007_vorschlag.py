"""Vorschläge für die Texte des Briefbogens über die KI-Schnittstelle (Gesamtaudit 15.11.,
MCP-01, Fachfrage FF-12 a). Neue Tabelle mit Zeilenschutz je Einheit; die vorige Fassung
kennt sie nicht und läuft unverändert. Rückweg: Tabelle entfernen.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLE = "letterhead_letterheadproposal"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql(TABLE))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [
        ("letterhead", "0006_name_und_logo_im_briefkopf"),
        ("mcpserver", "0003_fruehere_erneuerungen"),
        ("organizations", "0072_db_default_rueckweg"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LetterheadProposal",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("texts", models.JSONField(default=dict)),
                ("via", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "grant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="mcpserver.mcpgrant",
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
                (
                    "target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vorschlag für den Briefbogen",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.RunPython(forwards, backwards),
    ]
