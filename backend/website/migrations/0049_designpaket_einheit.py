import django.db.models.deletion
from django.db import migrations, models

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLE = "website_designpackage"
# Pakete der Installation (ohne Einheit) sehen alle, die einer Einheit nur diese
VISIBLE = f"organization_id IS NULL OR organization_id = {ORG}"


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_policy_sql(TABLE, VISIBLE))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    """#481: Designpakete auch nur für eine Einheit, von deren Webseitenverwaltung eingespielt;
    Plattformverwalter können sie sperren. Neue Felder sind leer bzw. ``False`` (in der
    Datenbank vorbelegt), bisherige Pakete gelten weiter für die Installation. Das Kürzel
    ist ohne Einheit weiter eindeutig, mit Einheit nur innerhalb der Einheit; ältere Stände
    lesen die neuen Felder nicht. Zeilenschutz: Pakete einer Einheit sieht nur diese."""

    dependencies = [
        ("organizations", "0070_farbrollen"),
        ("website", "0048_menue_platz"),
    ]

    operations = [
        migrations.AddField(
            model_name="designpackage",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="organizations.organization",
                verbose_name="nur für Einheit",
            ),
        ),
        migrations.AddField(
            model_name="designpackage",
            name="blocked",
            field=models.BooleanField(db_default=False, default=False, verbose_name="gesperrt"),
        ),
        migrations.AlterField(
            model_name="designpackage",
            name="key",
            field=models.CharField(max_length=40, verbose_name="Kürzel"),
        ),
        migrations.AddConstraint(
            model_name="designpackage",
            constraint=models.UniqueConstraint(
                condition=models.Q(organization__isnull=True),
                fields=("key",),
                name="designpaket_kuerzel_installation",
            ),
        ),
        migrations.AddConstraint(
            model_name="designpackage",
            constraint=models.UniqueConstraint(
                fields=("organization", "key"), name="designpaket_kuerzel_einheit"
            ),
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
