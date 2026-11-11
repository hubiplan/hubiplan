"""Geschäftspartner P5: Verträge mit Kündigungsfrist und Dokumente an der Akte."""

import billing.models
import core.encfields
import django.db.models.deletion
import exchange.models
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql("billing_partnerdocument"))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("billing_partnerdocument"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0028_partner_vereinbarungen"),
        ("organizations", "0064_logo_dunkel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="partneragreement",
            name="auto_renew",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="partneragreement",
            name="notice_days",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="partneragreement",
            name="kind",
            field=models.CharField(
                choices=[
                    ("sponsoring", "Sponsoring"),
                    ("framework", "Rahmenvereinbarung"),
                    ("contract", "Vertrag"),
                    ("other", "Sonstige Vereinbarung"),
                ],
                default="sponsoring",
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="PartnerDocument",
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
                    "title",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=200, strict=True
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveIntegerField(default=0)),
                (
                    "file",
                    models.FileField(
                        storage=exchange.models.private_storage,
                        upload_to=billing.models.partner_document_path,
                    ),
                ),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agreement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="billing.partneragreement",
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
                        related_name="documents",
                        to="billing.businesspartner",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Dokument zum Geschäftspartner",
                "ordering": ["-uploaded_at", "pk"],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
