"""Versiegelte Protokolleinträge auch in der Datenbank schützen (Gesamtaudit 05.11. GA-08).

Sobald ein Eintrag in der Kette steht (``hash`` gesetzt), lassen sich Zeitpunkt, Aktion,
Objekt, Organisation und die Kettenfelder nicht mehr ändern. Leeren des Inhalts
(``changes``, ``object_repr``, ``cleared``) bleibt erlaubt: Löschfristen und Auskunft
nach DSGVO brauchen das, und die Kette bleibt über ``changes_hash`` prüfbar.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION audit_entry_sealed() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER audit_entry_sealed
    BEFORE UPDATE ON audit_auditentry
    FOR EACH ROW EXECUTE FUNCTION audit_entry_sealed();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS audit_entry_sealed ON audit_auditentry;
DROP FUNCTION IF EXISTS audit_entry_sealed();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD, params=None)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(BACKWARD)


class Migration(migrations.Migration):
    dependencies = [("audit", "0007_db_defaults")]

    operations = [migrations.RunPython(forwards, backwards)]
