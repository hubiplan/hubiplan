"""Scan-Links und eingelöste Zusatzleistungen: Zeilenschutz je Einheit wie die übrigen
Anmeldetabellen.

Rückweg: Schutz und Prüfung aufheben.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

PARENTS = {
    "registrations_scanlink": ("registrations_registrationsetup", "setup_id"),
    "registrations_redemption": ("registrations_booking", "booking_id"),
}


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    branches = []
    for table, (parent, column) in PARENTS.items():
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
        branches.append(f"""
          {"IF" if not branches else "ELSIF"} TG_TABLE_NAME = '{table}' THEN
            SELECT organization_id INTO parent_org FROM {parent} WHERE id = NEW.{column};""")
    schema_editor.execute(f"""
        CREATE FUNCTION registration_scan_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          {"".join(branches)}
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'registration scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in PARENTS:
        schema_editor.execute(f"""CREATE TRIGGER registration_scan_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION registration_scan_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in PARENTS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registration_scan_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS registration_scan_guard()")


class Migration(migrations.Migration):
    dependencies = [("registrations", "0010_scan_links")]

    operations = [migrations.RunPython(rls, no_rls)]
