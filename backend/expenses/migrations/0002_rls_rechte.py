"""Auslagen: Zeilenschutz je Verein und Rechte für bestehende Rollen.

Rollen, die die Finanzen sehen oder bearbeiten, sehen bzw. prüfen auch Auslagen.
Rückweg: Zeilenschutz aus, Codes entfernen.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = (
    "expenses_expensesettings",
    "expenses_expenseclaim",
    "expenses_expenseline",
    "expenses_expensefile",
    "expenses_expenseevent",
    "expenses_expenselink",
    "expenses_transferrun",
    "expenses_transferitem",
)
CHILDREN = ("expenses_expenseline", "expenses_expensefile", "expenses_expenseevent")
VIEW = "expenses.view"
EDIT = "expenses.edit"


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Positionen, Belege, Verlauf und Laufposten gehören zum Verein ihrer Auslage
    schema_editor.execute("""
        CREATE FUNCTION expense_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'expenses_transferitem' THEN
            SELECT organization_id INTO parent_org FROM expenses_transferrun WHERE id = NEW.run_id;
            IF parent_org IS DISTINCT FROM NEW.organization_id THEN
              RAISE EXCEPTION 'expense scope mismatch' USING ERRCODE = '23514';
            END IF;
          END IF;
          SELECT organization_id INTO parent_org FROM expenses_expenseclaim WHERE id = NEW.claim_id;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'expense scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in (*CHILDREN, "expenses_transferitem"):
        schema_editor.execute(f"""CREATE TRIGGER expense_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION expense_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in (*CHILDREN, "expenses_transferitem"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS expense_scope_guard ON {table}")
    for table in TABLES:
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS expense_scope_guard()")


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.filter(organization__type="club").iterator():
        perms = set(role.permissions or [])
        add = set()
        if "finance.view" in perms or "finance.edit" in perms:
            add.add(VIEW)
        if "finance.edit" in perms:
            add.add(EDIT)
        if add - perms:
            Role._base_manager.filter(pk=role.pk).update(permissions=sorted(perms | add))


def revoke(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in (VIEW, EDIT)]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0001_auslagen"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
