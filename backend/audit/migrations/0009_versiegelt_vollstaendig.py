"""Versiegelte Protokolleinträge vollständig in der Datenbank schützen.

Ergänzt den Trigger aus audit/0008 um alle übrigen gehashten Felder aus ``entry_digest()``
(``id``, ``user_email``, ``person_id``, ``change_set``, ``via``). Das Leeren von Inhalt
und Bezeichnung (``changes``, ``object_repr``, ``cleared``) für DSGVO-Löschfristen bleibt
erlaubt.

Rückweg: Die Rückwärtsmigration stellt den Trigger aus audit/0008 wieder her.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_entry_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.hash <> '' AND
       (NEW.id, NEW.organization_id, NEW.user_email, NEW.timestamp, NEW.action,
        NEW.object_type, NEW.object_id, NEW.person_id, NEW.change_set, NEW.via,
        NEW.seq, NEW.prev_hash, NEW.hash, NEW.changes_hash)
       IS DISTINCT FROM
       (OLD.id, OLD.organization_id, OLD.user_email, OLD.timestamp, OLD.action,
        OLD.object_type, OLD.object_id, OLD.person_id, OLD.change_set, OLD.via,
        OLD.seq, OLD.prev_hash, OLD.hash, OLD.changes_hash) THEN
        RAISE EXCEPTION 'Protokolleintrag % ist versiegelt.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

BACKWARD = """
CREATE OR REPLACE FUNCTION audit_entry_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.hash <> '' AND
       (NEW.organization_id, NEW.timestamp, NEW.action, NEW.object_type, NEW.object_id,
        NEW.seq, NEW.prev_hash, NEW.hash, NEW.changes_hash)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.timestamp, OLD.action, OLD.object_type, OLD.object_id,
        OLD.seq, OLD.prev_hash, OLD.hash, OLD.changes_hash) THEN
        RAISE EXCEPTION 'Protokolleintrag % ist versiegelt.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD, params=None)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(BACKWARD, params=None)


class Migration(migrations.Migration):
    dependencies = [("audit", "0008_versiegelt_unveraenderbar")]

    operations = [migrations.RunPython(forwards, backwards)]
