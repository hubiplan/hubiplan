"""GoBD-Datenbanktrigger und Schutz bestehender Finanzverweise härten.

1. ``finance_receipt_gobd`` gilt für ``BEFORE UPDATE OR DELETE`` (schützt ``booking_id``,
   ``organization_id``, ``file``, ``content_type``, ``size``, ``einvoice`` vor Änderung).
2. ``finance_gobd_freigeben_belege`` prüft den Zeitraum gegen das Geschäftsjahr ``fy`` und
   ``finance_gobd_beleg_frei`` zusätzlich ``b.year = f.jahr``.
3. ``finance_booking_gobd`` schützt zusätzlich ``vat_rate``, ``input_tax_share``,
   ``split_of_id`` und ``is_opening`` (weiterhin änderbar bleiben Text/Gegenseite/Referenz
   für Schlüsselwechsel & Anonymisierung sowie Projekt/Vergütung/Zweckbindung/frozen).
4. ``BudgetLine.department`` und ``CashAuditAccount.account`` erhalten ``on_delete=PROTECT``
   und der unnutzbare B-Tree-Index auf verschlüsseltem ``Booking.counterparty`` entfällt.

Rückweg: Die Rückwärtsmigration stellt den Stand aus finance/0032 wieder her; die vorige
Fassung arbeitet unverändert mit dem gehärteten Trigger weiter.
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

CREATE OR REPLACE FUNCTION finance_gobd_beleg_frei(org bigint, bid bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM finance_gobd_freigabe f
        JOIN finance_booking b ON b.id = bid AND b.organization_id = f.organization_id
        WHERE f.xact = pg_current_xact_id_if_assigned() AND f.organization_id = org
          AND f.art = 'belege' AND b.year = f.jahr AND b.date BETWEEN f.von AND f.bis
    );
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
        NEW.vat_rate, NEW.input_tax_share, NEW.split_of_id, NEW.is_opening)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.year, OLD.number, OLD.date, OLD.kind, OLD.amount,
        OLD.account_id, OLD.to_account_id, OLD.category_id, OLD.cancels_id,
        OLD.vat_rate, OLD.input_tax_share, OLD.split_of_id, OLD.is_opening) THEN
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
        IF (NEW.organization_id, NEW.booking_id, NEW.file, NEW.content_type, NEW.size, NEW.einvoice)
           IS DISTINCT FROM
           (OLD.organization_id, OLD.booking_id, OLD.file, OLD.content_type, OLD.size, OLD.einvoice) THEN
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

CREATE OR REPLACE FUNCTION finance_gobd_beleg_frei(org bigint, bid bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM finance_gobd_freigabe f
        JOIN finance_booking b ON b.id = bid AND b.organization_id = f.organization_id
        WHERE f.xact = pg_current_xact_id_if_assigned() AND f.organization_id = org
          AND f.art = 'belege' AND b.date BETWEEN f.von AND f.bis
    );
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
        migrations.RemoveIndex(
            model_name="booking",
            name="finance_boo_organiz_df997e_idx",
        ),
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
