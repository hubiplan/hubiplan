"""Festgeschriebene Rechnungen in der Datenbank schützen (Datenaudit 08.11., DR-01/DR-02, FD-11).

Wie bei Buchungen (finance/0024, 0032): Eine Rechnung mit Nummer lässt sich nicht löschen.
Nummer, Geschäftsjahr, Datum und Einheit bleiben nach dem Festschreiben unverändert, und sie
wird nicht wieder Entwurf. Zahlung, Mahnung, Storno und Anonymisierung ändern andere Felder
und bleiben möglich. Einzige Ausnahme ist das ausdrückliche Löschen einer ganzen Einheit über
``finance_gobd_freigeben_einheit`` (finance/gobd.py ``release_unit``).

Den Empfänger prüft der Trigger nicht: Der Name ist verschlüsselt (Schlüsselwechsel schreibt
ihn neu), und nach Ablauf der Aufbewahrungsfrist wird er anonymisiert.

Rückweg: Die Rückwärtsmigration entfernt Trigger und Funktion; die Anwendung der Vorfassung
läuft mit und ohne Trigger.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION billing_invoice_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.number IS NULL OR finance_gobd_einheit_frei(OLD.organization_id) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Rechnung % ist festgeschrieben und kann nicht geloescht werden.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (NEW.organization_id, NEW.year, NEW.number, NEW.date)
       IS DISTINCT FROM (OLD.organization_id, OLD.year, OLD.number, OLD.date)
       OR NEW.status = 'draft' THEN
        RAISE EXCEPTION 'Rechnung % ist festgeschrieben; nur Storno ist moeglich.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER billing_invoice_gobd
    BEFORE UPDATE OR DELETE ON billing_invoice
    FOR EACH ROW EXECUTE FUNCTION billing_invoice_gobd();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS billing_invoice_gobd ON billing_invoice;
DROP FUNCTION IF EXISTS billing_invoice_gobd();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD, params=None)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(BACKWARD, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0023_stornorechnung"),
        ("finance", "0032_gobd_freigabe"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
