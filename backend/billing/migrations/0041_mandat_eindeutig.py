"""Höchstens ein gültiges SEPA-Mandat je Zahler, auch bei gleichzeitigen Anfragen
(Sicherheitsprüfung 26.11.2026, B-M07).

Die Anwendung ersetzt beim Erteilen das alte Mandat. Zwei gleichzeitige Anfragen konnten
bisher beide ein gültiges Mandat anlegen; jetzt verhindert das die Datenbank.

Rückweg: Die Rückwärtsmigration entfernt die Regeln wieder. Die vorige Fassung der Anwendung
läuft mit ihnen weiter (sie legt je Zahler ebenfalls nur ein gültiges Mandat an).
"""

from django.db import migrations, models

# Sollten durch gleichzeitige Anfragen schon zwei gültige Mandate desselben Zahlers
# entstanden sein, gilt das jüngste; die älteren werden wie beim Ersetzen widerrufen.
# Ohne diesen Schritt schlüge das Anlegen der Indizes auf solchen Beständen fehl.
DEDUPE = """
UPDATE billing_mandate m
SET status = 'revoked', revoked_on = CURRENT_DATE
WHERE m.status = 'active' AND EXISTS (
    SELECT 1 FROM billing_mandate n
    WHERE n.status = 'active' AND n.organization_id = m.organization_id AND n.id > m.id
      AND (
        (m.membership_id IS NOT NULL AND n.membership_id = m.membership_id)
        OR (m.club_id IS NOT NULL AND n.club_id = m.club_id)
        OR (m.household_id IS NOT NULL AND n.household_id = m.household_id)
      )
);
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0040_arbeitsstunden")]

    operations = [
        migrations.RunSQL(DEDUPE, migrations.RunSQL.noop),
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
    ]
