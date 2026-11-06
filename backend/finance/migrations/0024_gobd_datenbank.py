"""Festgeschriebene Buchungen auch in der Datenbank schützen (Gesamtaudit 05.11. GA-08).

Bisher galten die GoBD-Sperren nur in der Anwendung; die Datenbankrolle der Anwendung
durfte jede Buchung ändern oder löschen. Ein Trigger verhindert jetzt bei Buchungen in
einem abgeschlossenen Geschäftsjahr oder bis „Kasse festgeschrieben bis“:

- Ändern von Betrag, Art, Datum, Nummer, Geschäftsjahr, Konten, Kategorie, Storno-Bezug,
- Löschen,
- Löschen ihrer Belege.

Text, Gegenseite und Referenz bleiben änderbar (Schlüsselwechsel, Anonymisieren nach der
Aufbewahrungsfrist). Die monatliche automatische Festschreibung prüft weiter nur die
Anwendung (sie hängt vom heutigen Datum ab). Das ausdrückliche Löschen einer ganzen
Einheit und der Löschlauf nach Ablauf der Aufbewahrungsfrist setzen ``app.gobd_erasure``
für die eigene Transaktion (``finance.gobd``).
"""

from django.db import migrations

from core.rls import APP_ROLE

FORWARD = """
CREATE FUNCTION finance_booking_fixed(org bigint, fy integer, d date)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM finance_yearclosing c WHERE c.organization_id = org AND c.year = fy
    ) OR EXISTS (
        SELECT 1 FROM organizations_organization o
        WHERE o.id = org AND o.finance_locked_until IS NOT NULL AND d <= o.finance_locked_until
    );
$$;

CREATE FUNCTION finance_booking_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('app.gobd_erasure', true), '') = 'on' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF NOT finance_booking_fixed(OLD.organization_id, OLD.year, OLD.date) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Buchung % ist festgeschrieben und kann nicht geloescht werden.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (NEW.organization_id, NEW.year, NEW.number, NEW.date, NEW.kind, NEW.amount,
        NEW.account_id, NEW.to_account_id, NEW.category_id, NEW.cancels_id)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.year, OLD.number, OLD.date, OLD.kind, OLD.amount,
        OLD.account_id, OLD.to_account_id, OLD.category_id, OLD.cancels_id) THEN
        RAISE EXCEPTION 'Buchung % ist festgeschrieben; nur Storno ist moeglich.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER finance_booking_gobd
    BEFORE UPDATE OR DELETE ON finance_booking
    FOR EACH ROW EXECUTE FUNCTION finance_booking_gobd();

-- Ohne Zeilensicherheit: auch eine für die Anfrage unsichtbare Buchung zählt
CREATE FUNCTION finance_booking_id_fixed(bid bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT coalesce((
        SELECT finance_booking_fixed(b.organization_id, b.year, b.date)
        FROM finance_booking b WHERE b.id = bid
    ), false);
$$;

CREATE FUNCTION finance_receipt_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('app.gobd_erasure', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    IF finance_booking_id_fixed(OLD.booking_id) THEN
        RAISE EXCEPTION 'Beleg % gehoert zu einer festgeschriebenen Buchung.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER finance_receipt_gobd
    BEFORE DELETE ON finance_receipt
    FOR EACH ROW EXECUTE FUNCTION finance_receipt_gobd();

REVOKE ALL ON FUNCTION finance_booking_fixed(bigint, integer, date) FROM PUBLIC;
REVOKE ALL ON FUNCTION finance_booking_id_fixed(bigint) FROM PUBLIC;
"""

BACKWARD = """
DROP TRIGGER IF EXISTS finance_receipt_gobd ON finance_receipt;
DROP FUNCTION IF EXISTS finance_receipt_gobd();
DROP FUNCTION IF EXISTS finance_booking_id_fixed(bigint);
DROP TRIGGER IF EXISTS finance_booking_gobd ON finance_booking;
DROP FUNCTION IF EXISTS finance_booking_gobd();
DROP FUNCTION IF EXISTS finance_booking_fixed(bigint, integer, date);
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD, params=None)
    # Die Rolle der Anwendung ruft die Hilfsfunktion im Trigger auf
    for signature in ("finance_booking_fixed(bigint, integer, date)", "finance_booking_id_fixed(bigint)"):
        schema_editor.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(BACKWARD)


class Migration(migrations.Migration):
    dependencies = [("finance", "0023_namenskopien_verschluesselt")]

    operations = [migrations.RunPython(forwards, backwards)]
