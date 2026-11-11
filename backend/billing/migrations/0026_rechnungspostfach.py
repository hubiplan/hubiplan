"""Rechnungspostfach: E-Rechnungen aus Mails übernehmen (#374).

Rückweg: Die Vorfassung kennt die neuen Tabellen und die Spalte ``mail`` nicht. Die Spalte
darf leer sein, die Vorfassung legt Eingänge also weiter ohne sie an.
"""

import core.encfields
import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ["billing_incomingmailbox", "billing_incomingmail"]


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(enable_rls_sql(table))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0025_eingang_hintergrundpruefung"),
        ("organizations", "0064_logo_dunkel"),
    ]

    operations = [
        migrations.CreateModel(
            name="IncomingMail",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("message_hash", models.CharField(blank=True, max_length=64)),
                (
                    "sender",
                    core.encfields.EncryptedEmailField(
                        blank=True, max_length=254, strict=True
                    ),
                ),
                (
                    "subject",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=300, strict=True
                    ),
                ),
                ("sender_known", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("imported", "Übernommen"),
                            ("no_invoice", "Keine E-Rechnung im Anhang"),
                            ("spam", "Als Spam markiert"),
                            ("virus", "Schadsoftware gefunden"),
                            ("error", "Nicht verarbeitet"),
                        ],
                        max_length=12,
                    ),
                ),
                ("skipped", models.JSONField(default=list)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("dismissed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-received_at", "-pk"],
            },
        ),
        migrations.AddField(
            model_name="incominginvoice",
            name="mail",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoices",
                to="billing.incomingmail",
            ),
        ),
        migrations.CreateModel(
            name="IncomingMailbox",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tag", models.CharField(max_length=20, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="incomingmail",
            index=models.Index(
                fields=["organization", "message_hash"],
                name="billing_inc_organiz_9d27d5_idx",
            ),
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
