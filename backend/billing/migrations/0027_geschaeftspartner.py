"""Geschäftspartner ausbauen (Konzept geschaeftspartner.md, P1).

Neue Spalten mit Standardwert in der Datenbank, damit die Vorfassung weiter Partner
anlegen kann (Rückweg: Vorfassung liest die Spalten nicht). Neue Tabelle mit RLS.
Rollen und Nummern bestehender Partner werden aus Kunde/Lieferant abgeleitet.
"""

import django.db.models.deletion
from django.db import migrations, models

import core.encfields
from core.rls import disable_rls_sql, enable_rls_sql


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql("billing_partnercontact"))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("billing_partnercontact"))


def roles_and_numbers(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    BusinessPartner = apps.get_model("billing", "BusinessPartner")
    counters = {}
    for partner in BusinessPartner.objects.order_by("organization_id", "pk"):
        roles = []
        if partner.is_customer:
            roles.append("customer")
        if partner.is_supplier:
            roles.append("supplier")
        counters[partner.organization_id] = counters.get(partner.organization_id, 0) + 1
        BusinessPartner.objects.filter(pk=partner.pk).update(
            roles=roles, number=f"GP-{counters[partner.organization_id]:04d}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0026_rechnungspostfach"),
        ("finance", "0033_umsatzsteuer"),
        ("members", "0028_organisation_groesse"),
        ("organizations", "0064_logo_dunkel"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="businesspartner",
            options={"ordering": ["pk"], "verbose_name": "Geschäftspartner"},
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="artist",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="bank",
            field=models.JSONField(blank=True, db_default={}, default=dict),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="default_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="finance.category",
            ),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="kind",
            field=models.CharField(
                choices=[
                    ("company", "Firma"),
                    ("authority", "Behörde/Amt"),
                    ("association", "Verein/Verband"),
                    ("person", "Privatperson"),
                    ("other", "Sonstiges"),
                ],
                db_default="company",
                default="company",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="membership",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="business_partners",
                to="members.membership",
            ),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="notes",
            field=models.TextField(blank=True, db_default="", default="", max_length=5000),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="number",
            field=models.CharField(blank=True, db_default="", default="", max_length=20),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="our_customer_number",
            field=core.encfields.EncryptedCharField(
                blank=True, db_default="", default="", max_length=60, strict=True
            ),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="payment_terms_days",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="roles",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="organizations.organization",
            ),
        ),
        migrations.CreateModel(
            name="PartnerContact",
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
                    "last_name",
                    core.encfields.EncryptedCharField(
                        max_length=100, strict=True, verbose_name="Name"
                    ),
                ),
                (
                    "first_name",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=100, strict=True, verbose_name="Vorname"
                    ),
                ),
                (
                    "function",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=100, strict=True, verbose_name="Funktion"
                    ),
                ),
                (
                    "email",
                    core.encfields.EncryptedEmailField(
                        blank=True,
                        max_length=254,
                        strict=True,
                        verbose_name="E-Mail-Adresse",
                    ),
                ),
                (
                    "phone",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=50, strict=True, verbose_name="Telefon"
                    ),
                ),
                (
                    "is_primary",
                    models.BooleanField(default=False, verbose_name="Hauptansprechpartner"),
                ),
                (
                    "receives_invoices",
                    models.BooleanField(default=False, verbose_name="erhält Rechnungen"),
                ),
                (
                    "receives_mail",
                    models.BooleanField(default=True, verbose_name="erhält Post"),
                ),
                (
                    "notes",
                    core.encfields.EncryptedCharField(
                        blank=True, max_length=500, strict=True, verbose_name="Notiz"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                        related_name="contacts",
                        to="billing.businesspartner",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ansprechpartner",
                "ordering": ["-is_primary", "pk"],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
        migrations.RunPython(roles_and_numbers, migrations.RunPython.noop),
    ]
