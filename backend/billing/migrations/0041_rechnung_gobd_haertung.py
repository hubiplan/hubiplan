"""GoBD-Schutz für festgeschriebene Rechnungen und Rechnungsposten härten sowie
Eindeutigkeit aktiver SEPA-Mandate je Zahler in der Datenbank absichern.

Rückweg: Die Rückwärtsmigration stellt billing_invoice_gobd auf den Stand aus billing/0024
zurück und entfernt den Trigger auf billing_invoiceline sowie die partiellen Unique-Indizes;
die vorige Fassung läuft mit und ohne diese Regeln weiter.
"""

from django.db import migrations, models

FORWARD = """
CREATE OR REPLACE FUNCTION billing_invoice_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.number IS NULL OR finance_gobd_einheit_frei(OLD.organization_id) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Rechnung % ist festgeschrieben und kann nicht geloescht werden.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (NEW.organization_id, NEW.year, NEW.number, NEW.date, NEW.due_date, NEW.total, NEW.prepaid)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.year, OLD.number, OLD.date, OLD.due_date, OLD.total, OLD.prepaid)
       OR NEW.status = 'draft' THEN
        RAISE EXCEPTION 'Rechnung % ist festgeschrieben; nur Storno ist moeglich.', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION billing_invoiceline_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    inv_id bigint;
    inv_org bigint;
    inv_num integer;
BEGIN
    inv_id := CASE WHEN TG_OP = 'INSERT' THEN NEW.invoice_id ELSE OLD.invoice_id END;
    SELECT i.organization_id, i.number INTO inv_org, inv_num
    FROM billing_invoice i WHERE i.id = inv_id;
    IF inv_num IS NULL OR finance_gobd_einheit_frei(inv_org) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'INSERT' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Rechnungsposten einer festgeschriebenen Rechnung sind unveraenderbar.'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (NEW.organization_id, NEW.invoice_id, NEW.position, NEW.amount, NEW.vat_rate)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.invoice_id, OLD.position, OLD.amount, OLD.vat_rate) THEN
        RAISE EXCEPTION 'Rechnungsposten einer festgeschriebenen Rechnung sind unveraenderbar.'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS billing_invoiceline_gobd ON billing_invoiceline;
CREATE TRIGGER billing_invoiceline_gobd
    BEFORE INSERT OR UPDATE OR DELETE ON billing_invoiceline
    FOR EACH ROW EXECUTE FUNCTION billing_invoiceline_gobd();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS billing_invoiceline_gobd ON billing_invoiceline;
DROP FUNCTION IF EXISTS billing_invoiceline_gobd();

CREATE OR REPLACE FUNCTION billing_invoice_gobd() RETURNS trigger LANGUAGE plpgsql AS $$
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
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD, params=None)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(BACKWARD, params=None)


class Migration(migrations.Migration):
    dependencies = [("billing", "0040_arbeitsstunden")]

    operations = [
        migrations.AddConstraint(
            model_name="mandate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("membership__isnull", False), ("status", "active")),
                fields=("organization", "membership"),
                name="mandat_aktiv_mitglied",
            ),
        ),
        migrations.AddConstraint(
            model_name="mandate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("club__isnull", False), ("status", "active")),
                fields=("organization", "club"),
                name="mandat_aktiv_verein",
            ),
        ),
        migrations.AddConstraint(
            model_name="mandate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("household__isnull", False), ("status", "active")),
                fields=("organization", "household"),
                name="mandat_aktiv_haushalt",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
