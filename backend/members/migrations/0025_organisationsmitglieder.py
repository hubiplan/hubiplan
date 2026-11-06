"""Organisationen (Firma, Verein, Behörde …) als Mitglieder (Konzept juristische Personen, J1).

Bestehende Zeilen werden Personen (``db_default``). Ältere Fassungen schreiben weiter ohne
Mitgliedstyp und bleiben damit beschreibbar. Der Trigger entwertet die Suchmarken jetzt auch
bei einem Wechsel des Mitgliedstyps.
"""

import core.encfields
from django.db import migrations, models

DROP_TRIGGER = "DROP TRIGGER members_person_marks_invalidate ON members_person;"

FUNCTION = """
CREATE OR REPLACE FUNCTION members_person_marks_invalidate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.scope_id, OLD.kind, OLD.last_name, OLD.first_name, OLD.birth_date,
           OLD.birth_year_only)
        IS DISTINCT FROM
       ROW(NEW.scope_id, NEW.kind, NEW.last_name, NEW.first_name, NEW.birth_date,
           NEW.birth_year_only)
    THEN
        NEW.last_birth_mark := '';
        NEW.first_birth_mark := '';
        NEW.last_year_mark := '';
        NEW.first_year_mark := '';
        NEW.marks_version := 0;
        NEW.marks_key_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;
"""

OLD_FUNCTION = """
CREATE OR REPLACE FUNCTION members_person_marks_invalidate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.scope_id, OLD.last_name, OLD.first_name, OLD.birth_date, OLD.birth_year_only)
        IS DISTINCT FROM
       ROW(NEW.scope_id, NEW.last_name, NEW.first_name, NEW.birth_date, NEW.birth_year_only)
    THEN
        NEW.last_birth_mark := '';
        NEW.first_birth_mark := '';
        NEW.last_year_mark := '';
        NEW.first_year_mark := '';
        NEW.marks_version := 0;
        NEW.marks_key_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;
"""

CREATE_TRIGGER = """
CREATE TRIGGER members_person_marks_invalidate
BEFORE UPDATE OF scope_id, kind, last_name, first_name, birth_date, birth_year_only
ON members_person FOR EACH ROW EXECUTE FUNCTION members_person_marks_invalidate();
"""

OLD_TRIGGER = """
CREATE TRIGGER members_person_marks_invalidate
BEFORE UPDATE OF scope_id, last_name, first_name, birth_date, birth_year_only
ON members_person FOR EACH ROW EXECUTE FUNCTION members_person_marks_invalidate();
"""

LEGAL_FORMS = [
    ("gmbh", "GmbH"),
    ("ug", "UG (haftungsbeschränkt)"),
    ("ag", "AG"),
    ("ev", "eingetragener Verein (e. V.)"),
    ("verein", "nicht eingetragener Verein"),
    ("eg", "Genossenschaft (eG)"),
    ("kg", "KG / GmbH & Co. KG"),
    ("ohg", "oHG"),
    ("gbr", "GbR"),
    ("stiftung", "Stiftung"),
    ("koerperschaft", "Körperschaft des öffentlichen Rechts"),
    ("gebiet", "Gebietskörperschaft (Stadt, Gemeinde, Kreis)"),
    ("other", "Sonstige"),
]


def _text(name, verbose, length):
    return migrations.AddField(
        model_name="person",
        name=name,
        field=models.CharField(
            verbose, blank=True, db_default="", default="", max_length=length
        ),
    )


class Migration(migrations.Migration):
    dependencies = [("members", "0024_namen_verschluesselt")]

    operations = [
        migrations.RunSQL(DROP_TRIGGER, reverse_sql=OLD_TRIGGER),
        migrations.AddField(
            model_name="person",
            name="kind",
            field=models.CharField(
                "Mitgliedstyp",
                choices=[("person", "Person"), ("organization", "Organisation")],
                db_default="person",
                default="person",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="legal_form",
            field=models.CharField(
                "Rechtsform",
                blank=True,
                choices=LEGAL_FORMS,
                db_default="",
                default="",
                max_length=20,
            ),
        ),
        _text("legal_form_other", "Rechtsform (Freitext)", 100),
        _text("name_suffix", "Namenszusatz", 100),
        _text("register", "Register (Gericht und Nummer)", 100),
        _text("vat_id", "USt-IdNr.", 20),
        _text("website", "Webseite", 200),
        migrations.AlterField(
            model_name="person",
            name="birth_date",
            field=core.encfields.EncryptedDateField("Geburtsdatum", blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="person",
            name="first_name",
            field=core.encfields.EncryptedCharField(
                "Vorname", blank=True, max_length=100, strict=True
            ),
        ),
        migrations.AddConstraint(
            model_name="person",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind", "organization"), ("birth_date__isnull", False), _connector="OR"),
                name="person_birth_date_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="person",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["person", "organization"])),
                name="person_kind_valid",
            ),
        ),
        migrations.RunSQL(FUNCTION, reverse_sql=OLD_FUNCTION),
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
