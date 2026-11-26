"""GoBD-Sperren der Datenbank vervollständigen (Sicherheitsprüfung 26.11.2026, B-H01, B-M05).

1. Belege festgeschriebener Buchungen lassen sich auch nicht mehr umhängen oder austauschen:
   ``finance_receipt_gobd`` gilt jetzt für ``UPDATE`` und schützt Einheit, Buchung, Datei,
   Dateityp und Größe. Ausblenden mit Grund und der Schlüsselwechsel bleiben möglich.
2. Die Freigabe der Belege nach Ablauf der Aufbewahrungsfrist nimmt nur noch einen Zeitraum
   innerhalb des genannten Geschäftsjahres an. Sonst ließen sich Belege eines Jahres mit
   Löschsperre über ein anderes Jahr freigeben.
3. Festgeschriebene Buchungen behalten auch Steuersatz, Vorsteueranteil und den Verweis auf
   den Kopf einer Splitbuchung. Text, Gegenseite, Referenz, Veranstaltung, Vergütung und
   Zweckbindung bleiben änderbar wie bisher.
4. ``BudgetLine.department`` und ``CashAuditAccount.account`` löschen ihre Zeilen nicht mehr
   mit (``PROTECT`` statt ``CASCADE``; nur in Django, keine Änderung an der Datenbank).

Rückweg: Die Rückwärtsmigration stellt den Stand aus finance/0032 wieder her. Die vorige
Fassung der Anwendung arbeitet auch mit den strengeren Sperren weiter.
"""

from django.db import migrations, models
import django.db.models.deletion

FORWARD = """
CREATE OR REPLACE FUNCTION finance_gobd_freigeben_belege(org bigint, fy integer, d_von date, d_bis date)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    m integer;
    d integer;
    fy_von date;
    fy_bis date;
BEGIN
    IF d_von IS NULL OR d_bis IS NULL OR d_bis < d_von OR d_bis - d_von > 400 THEN
        RAISE EXCEPTION 'Ungueltiger Zeitraum.' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT coalesce(o.fiscal_start_month, 1), coalesce(o.fiscal_start_day, 1)
    INTO m, d
    FROM organizations_organization o
    WHERE o.id = org;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unbekannte Organisation.' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    fy_von := make_date(fy, m, d);
    fy_bis := (fy_von + interval '1 year')::date - 1;
    IF d_von < fy_von OR d_bis > fy_bis THEN
        RAISE EXCEPTION 'Zeitraum passt nicht zum Geschaeftsjahr %.', fy
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM finance_yearclosing c
        WHERE c.organization_id = org AND c.year = fy AND c.retention_hold = ''
    ) THEN
        RAISE EXCEPTION 'Geschaeftsjahr % ist nicht abgeschlossen oder gesperrt.', fy
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF finance_gobd_heute() < make_date(extract(year FROM d_bis)::integer + 9, 1, 1) THEN
        RAISE EXCEPTION 'Aufbewahrungsfrist fuer Belege laeuft noch.'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    INSERT INTO finance_gobd_freigabe (organization_id, art, jahr, von, bis)
    VALUES (org, 'belege', fy, d_von, d_bis);
END;
$$;

CREATE OR REPLACE FUNCTION finance_booking_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF finance_gobd_einheit_frei(OLD.organization_id) THEN
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
        NEW.account_id, NEW.to_account_id, NEW.category_id, NEW.cancels_id,
        NEW.vat_rate, NEW.input_tax_share, NEW.split_of_id)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.year, OLD.number, OLD.date, OLD.kind, OLD.amount,
        OLD.account_id, OLD.to_account_id, OLD.category_id, OLD.cancels_id,
        OLD.vat_rate, OLD.input_tax_share, OLD.split_of_id) THEN
        RAISE EXCEPTION 'Buchung % ist festgeschrieben; nur Storno ist moeglich.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION finance_receipt_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF finance_gobd_einheit_frei(OLD.organization_id)
       OR finance_gobd_beleg_frei(OLD.organization_id, OLD.booking_id) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF finance_booking_id_fixed(OLD.booking_id) THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Beleg % gehoert zu einer festgeschriebenen Buchung.', OLD.id
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF (NEW.organization_id, NEW.booking_id, NEW.file, NEW.content_type, NEW.size)
           IS DISTINCT FROM
           (OLD.organization_id, OLD.booking_id, OLD.file, OLD.content_type, OLD.size) THEN
            RAISE EXCEPTION 'Beleg % gehoert zu einer festgeschriebenen Buchung.', OLD.id
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS finance_receipt_gobd ON finance_receipt;
CREATE TRIGGER finance_receipt_gobd
    BEFORE UPDATE OR DELETE ON finance_receipt
    FOR EACH ROW EXECUTE FUNCTION finance_receipt_gobd();
"""

BACKWARD = """
CREATE OR REPLACE FUNCTION finance_gobd_freigeben_belege(org bigint, fy integer, d_von date, d_bis date)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    IF d_von IS NULL OR d_bis IS NULL OR d_bis < d_von OR d_bis - d_von > 400 THEN
        RAISE EXCEPTION 'Ungueltiger Zeitraum.' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM finance_yearclosing c
        WHERE c.organization_id = org AND c.year = fy AND c.retention_hold = ''
    ) THEN
        RAISE EXCEPTION 'Geschaeftsjahr % ist nicht abgeschlossen oder gesperrt.', fy
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF finance_gobd_heute() < make_date(extract(year FROM d_bis)::integer + 9, 1, 1) THEN
        RAISE EXCEPTION 'Aufbewahrungsfrist fuer Belege laeuft noch.'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    INSERT INTO finance_gobd_freigabe (organization_id, art, jahr, von, bis)
    VALUES (org, 'belege', fy, d_von, d_bis);
END;
$$;

CREATE OR REPLACE FUNCTION finance_booking_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF finance_gobd_einheit_frei(OLD.organization_id) THEN
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

CREATE OR REPLACE FUNCTION finance_receipt_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF finance_gobd_einheit_frei(OLD.organization_id)
       OR finance_gobd_beleg_frei(OLD.organization_id, OLD.booking_id) THEN
        RETURN OLD;
    END IF;
    IF finance_booking_id_fixed(OLD.booking_id) THEN
        RAISE EXCEPTION 'Beleg % gehoert zu einer festgeschriebenen Buchung.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS finance_receipt_gobd ON finance_receipt;
CREATE TRIGGER finance_receipt_gobd
    BEFORE DELETE ON finance_receipt
    FOR EACH ROW EXECUTE FUNCTION finance_receipt_gobd();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD, params=None)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(BACKWARD, params=None)


class Migration(migrations.Migration):
    dependencies = [("finance", "0039_bankanbindung")]

    operations = [
        migrations.AlterField(
            model_name="budgetline",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="organizations.department",
                verbose_name="Abteilung",
            ),
        ),
        migrations.AlterField(
            model_name="cashauditaccount",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="finance.account",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
