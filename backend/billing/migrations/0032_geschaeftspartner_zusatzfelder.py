"""Zusatzfelder für Geschäftspartner: zwei neue Tabellen mit RLS.

Rückweg: Die Vorfassung kennt die Tabellen nicht und liest sie nicht.
"""

import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ("billing_partnerfield", "billing_partnerfieldvalue")


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
        ("billing", "0031_geschaeftspartner_erstkontakt"),
        ("organizations", "0066_geschaeftspartner_im_menue"),
    ]

    operations = [
        migrations.CreateModel(
            name="PartnerField",
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
                ("label", models.CharField(max_length=100, verbose_name="Bezeichnung")),
                ("key", models.SlugField(verbose_name="Kennung")),
                (
                    "field_type",
                    models.CharField(default="text", max_length=10, verbose_name="Typ"),
                ),
                (
                    "choices",
                    models.JSONField(
                        blank=True, default=list, verbose_name="Auswahlwerte"
                    ),
                ),
                (
                    "repeatable",
                    models.BooleanField(default=False, verbose_name="wiederholbar"),
                ),
                (
                    "subfields",
                    models.JSONField(
                        blank=True, default=list, verbose_name="Unterfelder"
                    ),
                ),
                (
                    "help_text",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Hinweis"
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Reihenfolge"
                    ),
                ),
                (
                    "is_archived",
                    models.BooleanField(
                        default=False, verbose_name="nicht mehr verwendet"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
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
                "verbose_name": "Zusatzfeld für Geschäftspartner",
                "ordering": ["sort_order", "label"],
            },
        ),
        migrations.CreateModel(
            name="PartnerFieldValue",
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
                ("value", models.JSONField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="billing.partnerfield",
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
                    "partner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="field_values",
                        to="billing.businesspartner",
                    ),
                ),
            ],
            options={
                "verbose_name": "Zusatzfeld-Wert eines Geschäftspartners",
            },
        ),
        migrations.AddConstraint(
            model_name="partnerfield",
            constraint=models.UniqueConstraint(
                fields=("organization", "key"), name="partnerfeld_kennung_je_org"
            ),
        ),
        migrations.AddConstraint(
            model_name="partnerfieldvalue",
            constraint=models.UniqueConstraint(
                fields=("definition", "partner"), name="partnerfeldwert_einmal"
            ),
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
