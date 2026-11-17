"""Festgeschriebene Kasse auch für neue Buchungen und Datumsänderungen schützen (Gesamtaudit
15.11., PUB-08).

finance/0024 schützt Buchungen, die schon festgeschrieben sind (Ändern, Löschen). Neue
Buchungen mit einem Datum bis „Kasse festgeschrieben bis“ und das Verschieben einer Buchung in
diesen Zeitraum ließen sich aber noch anlegen. Ein weiterer Trigger weist jetzt ab:

- INSERT einer Buchung mit Datum bis „festgeschrieben bis“,
- UPDATE, das Datum, Betrag, Konto, Gegenkonto oder Kategorie ändert, wenn das alte oder das
  neue Datum im festgeschriebenen Zeitraum liegt (das alte prüft auch finance/0024).

Text, Gegenseite und Referenz bleiben änderbar (Anonymisieren, Schlüsselwechsel). Der Trigger
gilt nur für die ausdrückliche Festschreibung, nicht für abgeschlossene Geschäftsjahre (die
prüft die Anwendung; Abschlüsse legen keine Buchungen an). Eine Ausnahme über
Sitzungsvariablen gibt es nicht (finance/0032).

Abwärtsverträglich: Die vorige Fassung legt in diesem Zeitraum keine Buchungen an (die
Oberfläche prüft das jetzt ebenfalls); täte sie es, bekäme sie einen Fehler der Datenbank.
Rückweg: Trigger und Funktionen entfernen.
"""

from django.db import migrations

from core.rls import APP_ROLE

FORWARD = """
CREATE FUNCTION finance_booking_locked(org bigint, d date)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM organizations_organization o
        WHERE o.id = org AND o.finance_locked_until IS NOT NULL AND d <= o.finance_locked_until
    );
$$;
REVOKE ALL ON FUNCTION finance_booking_locked(bigint, date) FROM PUBLIC;

CREATE FUNCTION finance_booking_lock_new() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF finance_booking_locked(NEW.organization_id, NEW.date) THEN
            RAISE EXCEPTION 'Die Kasse ist bis zu diesem Datum festgeschrieben.'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF (NEW.date, NEW.amount, NEW.account_id, NEW.to_account_id, NEW.category_id)
       IS DISTINCT FROM
       (OLD.date, OLD.amount, OLD.account_id, OLD.to_account_id, OLD.category_id)
       AND (finance_booking_locked(NEW.organization_id, NEW.date)
            OR finance_booking_locked(OLD.organization_id, OLD.date)) THEN
        RAISE EXCEPTION 'Buchung % liegt in der festgeschriebenen Kasse.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER finance_booking_lock_new
    BEFORE INSERT OR UPDATE ON finance_booking
    FOR EACH ROW EXECUTE FUNCTION finance_booking_lock_new();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS finance_booking_lock_new ON finance_booking;
DROP FUNCTION IF EXISTS finance_booking_lock_new();
DROP FUNCTION IF EXISTS finance_booking_locked(bigint, date);
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD, params=None)
    schema_editor.execute(
        f"GRANT EXECUTE ON FUNCTION finance_booking_locked(bigint, date) TO {APP_ROLE}"
    )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(BACKWARD)


class Migration(migrations.Migration):
    dependencies = [("finance", "0036_haushaltsplan")]

    operations = [migrations.RunPython(forwards, backwards)]
