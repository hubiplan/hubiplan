"""Recht „Geschäftspartner“ für Rollen, die die Partner bisher über Kasse oder Beiträge
sahen oder pflegten (Konzept geschaeftspartner.md, P1). Rückweg: Code wieder entfernen."""

from django.db import migrations

VIEW = "partners.view"
EDIT = "partners.edit"


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forwards(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.filter(department__isnull=True).iterator():
        perms = set(role.permissions or [])
        add = set()
        if perms & {"finance.edit", "billing.edit"}:
            add = {VIEW, EDIT}
        elif perms & {"finance.view", "billing.view"}:
            add = {VIEW}
        if add - perms:
            Role._base_manager.filter(pk=role.pk).update(permissions=sorted(perms | add))


def backwards(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in (VIEW, EDIT)]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [("access", "0017_namenskopien_verschluesselt")]

    operations = [migrations.RunPython(forwards, backwards)]
