"""Bisher implizite Rollenhoheit bestehender Einstellungsrollen explizit erhalten."""

from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.select_related("organization").iterator():
        if role.department_id or role.organization.type == "platform":
            continue
        permissions = set(role.permissions or [])
        if permissions & {"settings.edit", "org.edit"}:
            permissions |= {"roles.view", "roles.edit"}
            Role._base_manager.filter(pk=role.pk).update(permissions=sorted(permissions))


class Migration(migrations.Migration):
    dependencies = [("access", "0016_bereiche")]
    # Rückweg lässt explizite Rechte stehen: spätere manuelle Vergaben dürfen nicht
    # verschwinden; auch die vorige Programmfassung versteht diese Codes bereits.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
