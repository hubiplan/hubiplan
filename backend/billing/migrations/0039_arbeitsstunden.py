"""Arbeitsstunden mit Ersatzbeitrag (docs/arbeitsstunden.md).

Neue Tabelle mit Zeilenschutz je Verein und Prüfung, dass die Mitgliedsart zum Verein gehört,
dazu zwei Felder mit null=True in den Beitragseinstellungen. Rückweg: die vorige Fassung
kennt Tabelle und Felder nicht und lässt sie unberührt.
"""

import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLE = "billing_workhourrule"


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(enable_rls_sql(TABLE))
    schema_editor.execute("""
        CREATE FUNCTION workhourrule_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM members_membertype
                         WHERE id = NEW.member_type_id AND organization_id = NEW.organization_id)
          THEN
            RAISE EXCEPTION 'workhourrule scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    schema_editor.execute(f"""CREATE TRIGGER workhourrule_scope_guard BEFORE INSERT OR UPDATE
        ON {TABLE} FOR EACH ROW EXECUTE FUNCTION workhourrule_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS workhourrule_scope_guard ON {TABLE}")
    schema_editor.execute("DROP FUNCTION IF EXISTS workhourrule_scope_guard()")
    schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0038_anmeldungen"),
        ("members", "0036_hinweis_volljaehrigkeit"),
        ("organizations", "0074_hilfe_rueckmeldung"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingsettings",
            name="work_max_age",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Arbeitsstunden bis Alter"
            ),
        ),
        migrations.AddField(
            model_name="billingsettings",
            name="work_min_age",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Arbeitsstunden ab Alter"
            ),
        ),
        migrations.CreateModel(
            name="WorkHourRule",
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
                    "hours",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=5,
                        verbose_name="Pflichtstunden im Jahr",
                    ),
                ),
                (
                    "rate",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        verbose_name="Ersatzbeitrag je fehlender Stunde",
                    ),
                ),
                (
                    "member_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_hour_rule",
                        to="members.membertype",
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
                "verbose_name": "Arbeitsstunden-Regel",
                "verbose_name_plural": "Arbeitsstunden-Regeln",
            },
        ),
        migrations.RunPython(rls, no_rls),
    ]
