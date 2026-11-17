"""Ermäßigung mit Nachweis: Zeilenschutz je Verein und Prüfung, dass Zuordnung, Nachweis,
Hinweis und Link zum Verein ihrer Ermäßigung und Mitgliedschaft (bzw. ihres Antrags) gehören.

Nur neue Tabellen. Rückweg: Zeilenschutz und Prüfung entfallen.
"""

from django.db import migrations

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = (
    "feeproofs_proofdiscount",
    "feeproofs_discountassignment",
    "feeproofs_feeproof",
    "feeproofs_proofnotice",
    "feeproofs_prooflink",
    "feeproofs_proofsettings",
    "feeproofs_applicationproof",
)
CHILDREN = (
    "feeproofs_discountassignment",
    "feeproofs_feeproof",
    "feeproofs_proofnotice",
    "feeproofs_prooflink",
)


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_rls_sql(table))
    schema_editor.execute("""
        CREATE FUNCTION feeproof_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM feeproofs_proofdiscount
                         WHERE id = NEW.discount_id AND organization_id = NEW.organization_id)
             OR NOT EXISTS (SELECT 1 FROM members_membership
                         WHERE id = NEW.membership_id AND organization_id = NEW.organization_id)
          THEN
            RAISE EXCEPTION 'feeproof scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in CHILDREN:
        schema_editor.execute(f"""CREATE TRIGGER feeproof_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION feeproof_scope_guard()""")
    schema_editor.execute("""
        CREATE FUNCTION feeproof_application_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM feeproofs_proofdiscount
                         WHERE id = NEW.discount_id AND organization_id = NEW.organization_id)
             OR NOT EXISTS (SELECT 1 FROM admission_application
                         WHERE id = NEW.application_id AND organization_id = NEW.organization_id)
          THEN
            RAISE EXCEPTION 'feeproof scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    schema_editor.execute("""CREATE TRIGGER feeproof_application_guard BEFORE INSERT OR UPDATE
        ON feeproofs_applicationproof FOR EACH ROW EXECUTE FUNCTION feeproof_application_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in CHILDREN:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS feeproof_scope_guard ON {table}")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS feeproof_application_guard ON feeproofs_applicationproof"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS feeproof_scope_guard()")
    schema_editor.execute("DROP FUNCTION IF EXISTS feeproof_application_guard()")
    for table in TABLES:
        schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("feeproofs", "0001_ermaessigung_nachweis")]

    operations = [migrations.RunPython(rls, no_rls)]
