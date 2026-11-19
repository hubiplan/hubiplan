"""Unbestätigte Anmeldungen aus dem öffentlichen Formular: Zeilenschutz je Einheit.

Rückweg: Schutz und Prüfung aufheben.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLE = "registrations_pendingregistration"


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(enable_policy_sql(TABLE, f"organization_id = {ORG}"))
    schema_editor.execute("""
        CREATE FUNCTION registration_pending_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          SELECT organization_id INTO parent_org FROM registrations_registrationsetup
            WHERE id = NEW.setup_id;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'registration scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    schema_editor.execute(f"""CREATE TRIGGER registration_pending_guard BEFORE INSERT OR UPDATE
        ON {TABLE} FOR EACH ROW EXECUTE FUNCTION registration_pending_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registration_pending_guard ON {TABLE}")
    schema_editor.execute(disable_rls_sql(TABLE))
    schema_editor.execute("DROP FUNCTION IF EXISTS registration_pending_guard()")


class Migration(migrations.Migration):
    dependencies = [("registrations", "0006_oeffentliche_anmeldung")]

    operations = [migrations.RunPython(rls, no_rls)]
