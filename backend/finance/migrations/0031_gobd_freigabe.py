"""Ausnahmen vom Kassenschutz nur noch über geprüfte Datenbankfunktionen (Gesamtaudit 08.11., F-07 C).

Bisher hob die Sitzungsvariable ``app.gobd_erasure`` den Schutz festgeschriebener Buchungen
und Belege (finance/0024) auf. Die Rolle der Anwendung kann solche Variablen selbst setzen;
eingeschleuster Code hätte damit beliebige Buchungen löschen können.

Neu gibt es zwei Funktionen mit den Rechten des Eigentümers. Sie prüfen die Voraussetzungen
in der Datenbank und vermerken eine Freigabe für die laufende Transaktion in
``finance_gobd_freigabe``. Diese Tabelle kann die Rolle der Anwendung weder lesen noch
schreiben; die Einträge bleiben nach dem Commit als Nachweis stehen.

- ``finance_gobd_freigeben_einheit(org)``: ausdrückliches Löschen einer ganzen Einheit
  (nicht Plattform, nicht auf anderer Instanz).
- ``finance_gobd_freigeben_belege(org, jahr, von, bis)``: Belege eines abgeschlossenen
  Geschäftsjahrs ohne Löschsperre, frühestens ab Beginn des 9. Jahres nach dessen Ende.
  Gilt nur für Belege von Buchungen mit Datum in diesem Geschäftsjahr.

``finance_gobd_testdatum`` ersetzt in Tests das heutige Datum (nur der Eigentümer kann es
setzen; im Betrieb leer).

Rückweg: die Rückwärtsmigration stellt die Trigger aus finance/0024 wieder her.
"""

from django.db import migrations

from core.rls import APP_ROLE

FORWARD = f"""
CREATE TABLE finance_gobd_freigabe (
    id bigserial PRIMARY KEY,
    xact xid8 NOT NULL DEFAULT pg_current_xact_id(),
    organization_id bigint NOT NULL,
    art text NOT NULL CHECK (art IN ('einheit', 'belege')),
    jahr integer,
    von date,
    bis date,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finance_gobd_freigabe_xact ON finance_gobd_freigabe (xact);
REVOKE ALL ON finance_gobd_freigabe FROM PUBLIC, {APP_ROLE};
REVOKE ALL ON SEQUENCE finance_gobd_freigabe_id_seq FROM PUBLIC, {APP_ROLE};

CREATE TABLE finance_gobd_testdatum (heute date NOT NULL);
REVOKE ALL ON finance_gobd_testdatum FROM PUBLIC, {APP_ROLE};

CREATE FUNCTION finance_gobd_heute() RETURNS date
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT coalesce((SELECT max(heute) FROM finance_gobd_testdatum), current_date);
$$;

CREATE FUNCTION finance_gobd_freigeben_einheit(org bigint) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM organizations_organization o
        WHERE o.id = org AND o.type <> 'platform' AND NOT o.is_remote
    ) THEN
        RAISE EXCEPTION 'Einheit % kann nicht geloescht werden.', org
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    INSERT INTO finance_gobd_freigabe (organization_id, art) VALUES (org, 'einheit');
END;
$$;

CREATE FUNCTION finance_gobd_freigeben_belege(org bigint, fy integer, d_von date, d_bis date)
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

CREATE FUNCTION finance_gobd_einheit_frei(org bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM finance_gobd_freigabe f
        WHERE f.xact = pg_current_xact_id_if_assigned() AND f.organization_id = org
          AND f.art = 'einheit'
    );
$$;

CREATE FUNCTION finance_gobd_beleg_frei(org bigint, bid bigint) RETURNS boolean
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

REVOKE ALL ON FUNCTION finance_gobd_heute() FROM PUBLIC;
REVOKE ALL ON FUNCTION finance_gobd_freigeben_einheit(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION finance_gobd_freigeben_belege(bigint, integer, date, date) FROM PUBLIC;
REVOKE ALL ON FUNCTION finance_gobd_einheit_frei(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION finance_gobd_beleg_frei(bigint, bigint) FROM PUBLIC;
"""

GRANTS = (
    "finance_gobd_freigeben_einheit(bigint)",
    "finance_gobd_freigeben_belege(bigint, integer, date, date)",
    "finance_gobd_einheit_frei(bigint)",
    "finance_gobd_beleg_frei(bigint, bigint)",
)

BACKWARD = """
CREATE OR REPLACE FUNCTION finance_booking_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE OR REPLACE FUNCTION finance_receipt_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
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

DROP FUNCTION IF EXISTS finance_gobd_beleg_frei(bigint, bigint);
DROP FUNCTION IF EXISTS finance_gobd_einheit_frei(bigint);
DROP FUNCTION IF EXISTS finance_gobd_freigeben_belege(bigint, integer, date, date);
DROP FUNCTION IF EXISTS finance_gobd_freigeben_einheit(bigint);
DROP FUNCTION IF EXISTS finance_gobd_heute();
DROP TABLE IF EXISTS finance_gobd_testdatum;
DROP TABLE IF EXISTS finance_gobd_freigabe;
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD, params=None)
    for signature in GRANTS:
        schema_editor.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(BACKWARD, params=None)


class Migration(migrations.Migration):
    dependencies = [("finance", "0030_zweckbindung")]

    operations = [migrations.RunPython(forwards, backwards)]
