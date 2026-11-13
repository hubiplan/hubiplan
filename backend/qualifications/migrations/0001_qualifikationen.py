"""Qualifikationen mit Ablaufdatum: Arten je Einheit, Nachweise je Person.

Zeilenschutz je Organisation; ein Nachweis gehört zur Organisation seiner Art.
Rückweg: beide Tabellen entfallen (Daten gehen dabei verloren).
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ("qualificationtype", "qualification")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name in TABLES:
        schema_editor.execute(enable_rls_sql(f"qualifications_{name}"))
    schema_editor.execute("""
        CREATE FUNCTION qualification_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM qualifications_qualificationtype
                         WHERE id = NEW.kind_id AND organization_id = NEW.organization_id) THEN
            RAISE EXCEPTION 'qualification scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    schema_editor.execute("""CREATE TRIGGER qualification_scope_guard BEFORE INSERT OR UPDATE
        ON qualifications_qualification FOR EACH ROW EXECUTE FUNCTION qualification_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS qualification_scope_guard ON qualifications_qualification"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS qualification_scope_guard()")
    for name in TABLES:
        schema_editor.execute(disable_rls_sql(f"qualifications_{name}"))


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("members", "0031_titel"),
        ("organizations", "0068_abschluss_zu_zweit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QualificationType",
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
                ("name", models.CharField(max_length=100, verbose_name="Bezeichnung")),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=300, verbose_name="Beschreibung"
                    ),
                ),
                (
                    "validity_months",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(600)],
                        verbose_name="gültig für Monate",
                    ),
                ),
                (
                    "remind_days",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        default=60,
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(365)],
                        verbose_name="Erinnerung Tage vorher",
                    ),
                ),
                (
                    "inspection_only",
                    models.BooleanField(
                        default=False, verbose_name="nur Einsichtsvermerk"
                    ),
                ),
                (
                    "is_archived",
                    models.BooleanField(
                        default=False, verbose_name="nicht mehr verwendet"
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Reihenfolge"
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
                "verbose_name": "Qualifikationsart",
                "verbose_name_plural": "Qualifikationsarten",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="Qualification",
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
                ("acquired_on", models.DateField(verbose_name="erworben am")),
                (
                    "valid_until",
                    models.DateField(blank=True, null=True, verbose_name="gültig bis"),
                ),
                (
                    "note",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Bemerkung"
                    ),
                ),
                ("reminded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="qualifications",
                        to="members.person",
                    ),
                ),
                (
                    "kind",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="records",
                        to="qualifications.qualificationtype",
                        verbose_name="Qualifikation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Qualifikation",
                "verbose_name_plural": "Qualifikationen",
                "ordering": ["-acquired_on", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="qualificationtype",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"),
                name="qualifikationsart_je_organisation",
            ),
        ),
        migrations.AddIndex(
            model_name="qualification",
            index=models.Index(
                fields=["organization", "person"], name="qualificati_organiz_6b217e_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="qualification",
            index=models.Index(
                fields=["organization", "valid_until"],
                name="qualificati_organiz_6d45a4_idx",
            ),
        ),
        migrations.RunPython(rls, no_rls),
    ]
