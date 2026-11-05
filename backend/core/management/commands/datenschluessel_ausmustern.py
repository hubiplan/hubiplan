"""Eine geprüfte alte Generation mit ausdrücklicher Betriebsfreigabe ausmustern."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core import crypto
from core.keyinventory import retire
from core.keyrotation import rotation_lock
from core.tenancy import rls_bypass


class Command(BaseCommand):
    help = "Verpacktes Material einer unbenutzten alten Generation nach Freigabe entfernen."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", type=int, required=True)
        parser.add_argument("--schluessel", type=int, required=True)
        parser.add_argument("--pruefsumme", required=True)
        parser.add_argument("--freigabe", required=True)
        parser.add_argument("--schreiber-angehalten", action="store_true")
        parser.add_argument("--sicherungen-geprueft", action="store_true")
        parser.add_argument(
            "--probe",
            action="store_true",
            help="Nur Freigabe vor einer neuen Vorher-Sicherung prüfen.",
        )

    def handle(
        self,
        *args,
        organisation,
        schluessel,
        pruefsumme,
        freigabe,
        schreiber_angehalten=False,
        sicherungen_geprueft=False,
        probe=False,
        **options,
    ):
        if not schreiber_angehalten or not sicherungen_geprueft:
            raise CommandError(
                "Alle Leser/Schreiber anhalten und Backup-/Rückweg-Aufbewahrung "
                "ausdrücklich bestätigen."
            )
        if connection.in_atomic_block or not connection.get_autocommit():
            raise CommandError("Ausmusterung außerhalb einer übergeordneten Transaktion ausführen.")
        with rotation_lock(), rls_bypass():
            crypto.reset()
            changed = retire(organisation, schluessel, pruefsumme, freigabe, probe=probe)
        if probe:
            self.stdout.write("Ausmusterungs-Vorprüfung erfolgreich; nichts entfernt.")
            return
        self.stdout.write(
            f"Datenschlüssel {schluessel}: "
            + (
                "Schlüsselmaterial entfernt; Nachweis erhalten."
                if changed
                else "Bereits mit dieser Freigabe ausgemustert."
            )
        )
