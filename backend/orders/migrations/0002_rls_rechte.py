"""Sammelbestellungen: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen des Vereins, die Rechnungen, Material oder Anmeldungen bearbeiten, dürfen
Sammelbestellungen bearbeiten; wer Rechnungen oder Material sehen darf, sieht sie auch.
Rückweg: Codes entfernen, Zeilenschutz aus.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = (
    "orders_ordercampaign",
    "orders_orderarticle",
    "orders_memberorder",
    "orders_memberorderline",
)
VIEW = "orders.view"
EDIT = "orders.edit"
EDITORS = {"billing.edit", "material.edit", "registrations.edit"}
VIEWERS = {"billing.view", "material.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Artikel und Bestellungen gehören zur Organisation ihrer Sammelbestellung, Positionen zu der
    # ihrer Bestellung (und ihr Artikel zur selben Sammelbestellung), die Mitgliedschaft und die
    # Untereinheit zur selben Organisation
    schema_editor.execute("""
        CREATE FUNCTION orders_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'orders_ordercampaign' THEN
            IF NEW.department_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM organizations_organization
                 WHERE id = NEW.department_id AND type = 'unit'
                   AND organization_id = NEW.organization_id) THEN
              RAISE EXCEPTION 'orders scope mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          ELSIF TG_TABLE_NAME = 'orders_orderarticle' THEN
            SELECT organization_id INTO parent_org FROM orders_ordercampaign
             WHERE id = NEW.campaign_id;
          ELSIF TG_TABLE_NAME = 'orders_memberorder' THEN
            SELECT organization_id INTO parent_org FROM orders_ordercampaign
             WHERE id = NEW.campaign_id;
            IF NOT EXISTS (SELECT 1 FROM members_membership
                            WHERE id = NEW.membership_id
                              AND organization_id = NEW.organization_id) THEN
              RAISE EXCEPTION 'orders scope mismatch' USING ERRCODE = '23514';
            END IF;
          ELSE
            SELECT organization_id INTO parent_org FROM orders_memberorder
             WHERE id = NEW.order_id;
            IF NOT EXISTS (SELECT 1 FROM orders_orderarticle a
                             JOIN orders_memberorder o ON o.campaign_id = a.campaign_id
                            WHERE a.id = NEW.article_id AND o.id = NEW.order_id) THEN
              RAISE EXCEPTION 'orders scope mismatch' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'orders scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER orders_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION orders_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS orders_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS orders_scope_guard()")


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    rows = Role._base_manager.filter(organization__type="club")
    for role in rows.iterator():
        perms = set(role.permissions or [])
        add = set()
        if perms & EDITORS:
            add = {VIEW, EDIT}
        elif perms & VIEWERS:
            add = {VIEW}
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
        ("orders", "0001_bestellungen"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
