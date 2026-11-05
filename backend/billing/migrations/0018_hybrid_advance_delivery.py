import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models

import billing.models
import exchange.models
from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0017_eingangspruefungen"),
        ("organizations", "0046_loeschfrist_schonfrist"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="document_kind",
            field=models.CharField(
                choices=[("invoice", "invoice"), ("advance", "advance"), ("final", "final")],
                db_default="invoice",
                default="invoice",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="prepaid",
            field=models.DecimalField(
                db_default=Decimal("0.00"), decimal_places=2, default=Decimal("0.00"), max_digits=12
            ),
        ),
        migrations.AlterField(
            model_name="invoice",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Entwurf"),
                    ("open", "offen"),
                    ("paid", "bezahlt"),
                    ("settled", "Abgerechnet"),
                    ("cancelled", "storniert"),
                ],
                default="draft",
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name="InvoiceAdvance",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("snapshot", models.JSONField(default=dict)),
                ("active", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "advance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="final_allocations",
                        to="billing.invoice",
                    ),
                ),
                (
                    "final_invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="advance_allocations",
                        to="billing.invoice",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("active", True)),
                        fields=("advance",),
                        name="invoice_advance_one_active_final",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="InvoiceDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "document",
                    models.CharField(
                        choices=[("invoice", "invoice"), ("cancellation", "cancellation")],
                        max_length=12,
                    ),
                ),
                ("request_id", models.UUIDField(default=uuid.uuid4)),
                ("provider_signature", models.CharField(max_length=64)),
                ("provider_label", models.CharField(max_length=100)),
                ("sha256", models.CharField(max_length=64)),
                ("status", models.CharField(default="prepared", max_length=15)),
                ("receipt", models.JSONField(default=dict)),
                ("error_code", models.CharField(blank=True, max_length=30)),
                ("attempted_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deliveries",
                        to="billing.invoice",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("invoice", "document", "provider_signature"),
                        name="invoice_delivery_provider_document",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="InvoiceHybridArtifact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("document", models.CharField(default="invoice", max_length=12)),
                (
                    "pdf",
                    models.FileField(
                        storage=exchange.models.private_storage,
                        upload_to=billing.models.hybrid_file_path,
                    ),
                ),
                (
                    "xml",
                    models.FileField(
                        storage=exchange.models.private_storage,
                        upload_to=billing.models.hybrid_file_path,
                    ),
                ),
                (
                    "cii_report",
                    models.FileField(
                        storage=exchange.models.private_storage,
                        upload_to=billing.models.hybrid_file_path,
                    ),
                ),
                (
                    "pdf_report",
                    models.FileField(
                        storage=exchange.models.private_storage,
                        upload_to=billing.models.hybrid_file_path,
                    ),
                ),
                ("sha256", models.CharField(max_length=64)),
                ("xml_sha256", models.CharField(max_length=64)),
                ("source_sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="hybrid_artifacts",
                        to="billing.invoice",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("invoice", "document"), name="invoice_hybrid_document_once"
                    )
                ],
            },
        ),
        *[
            migrations.RunSQL(enable_rls_sql(table), disable_rls_sql(table))
            for table in [
                "billing_invoiceadvance",
                "billing_invoicehybridartifact",
                "billing_invoicedelivery",
            ]
        ],
    ]
