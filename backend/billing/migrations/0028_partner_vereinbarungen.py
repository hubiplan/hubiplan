"""Geschäftspartner P4: Vereinbarungen (Sponsoring) und Einwilligung für die Webseite."""

import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql("billing_partneragreement"))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("billing_partneragreement"))


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0027_geschaeftspartner"),
        ("finance", "0034_geschaeftspartner"),
        ("organizations", "0064_logo_dunkel"),
        ("todos", "0017_verbund_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="businesspartner",
            name="website_consent",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="website_url",
            field=models.URLField(blank=True, db_default="", default="", max_length=300),
        ),
        migrations.CreateModel(
            name="PartnerAgreement",
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
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("sponsoring", "Sponsoring"),
                            ("framework", "Rahmenvereinbarung"),
                            ("other", "Sonstige Vereinbarung"),
                        ],
                        default="sponsoring",
                        max_length=12,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("start", models.DateField()),
                ("end", models.DateField(blank=True, null=True)),
                (
                    "amount",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                ("in_kind", models.CharField(blank=True, default="", max_length=300)),
                ("benefits", models.JSONField(blank=True, default=list)),
                (
                    "benefits_text",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "tax_kind",
                    models.CharField(
                        choices=[
                            ("mention", "Nur Nennung (ohne Werbung)"),
                            ("advertising", "Aktive Werbung"),
                            ("none", "Keine Einnahme"),
                        ],
                        default="mention",
                        max_length=12,
                    ),
                ),
                ("remind_days", models.PositiveSmallIntegerField(default=60)),
                ("thanked_at", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="", max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="finance.category",
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
                        related_name="agreements",
                        to="billing.businesspartner",
                    ),
                ),
                (
                    "reminder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="todos.todo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vereinbarung",
                "ordering": ["-start", "pk"],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
