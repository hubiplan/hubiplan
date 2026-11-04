"""Datenschlüssel gezielt und wiederaufnehmbar wechseln; Schreiber vorher anhalten."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.crypto import KeyUnavailable
from core.keyrotation import Rotation, rotation_lock
from core.tenancy import rls_bypass


class Command(BaseCommand):
    help = "Datenschlüssel eines Schlüsselinhabers prüfen, wechseln oder den Wechsel fortsetzen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organisation", type=int, required=True, help="Nummer des Schlüsselinhabers."
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--probe", action="store_true", help="Bestand nur vorprüfen, nichts ändern."
        )
        mode.add_argument("--starten", action="store_true", help="Einen neuen Wechsel beginnen.")
        mode.add_argument(
            "--pruefen", action="store_true", help="Letzten Wechsel nur vollständig prüfen."
        )
        parser.add_argument(
            "--schreiber-angehalten",
            action="store_true",
            help="Bestätigt das Wartungsfenster mit angehaltenen Schreibdiensten.",
        )

    def handle(
        self,
        *args,
        organisation,
        probe=False,
        starten=False,
        pruefen=False,
        schreiber_angehalten=False,
        **options,
    ):
        if not (probe or pruefen):
            if not schreiber_angehalten:
                raise CommandError("Schreibdienste anhalten und --schreiber-angehalten angeben.")
            if connection.in_atomic_block or not connection.get_autocommit():
                raise CommandError(
                    "Schlüsselwechsel außerhalb einer übergeordneten Transaktion ausführen."
                )
        try:
            with rotation_lock(), rls_bypass():
                rotation = Rotation(organisation, self.stdout)
                if probe:
                    rotation.preflight()
                elif pruefen:
                    rotation.verify_latest()
                else:
                    rotation.run(start=starten)
        except KeyUnavailable:
            raise CommandError(
                "Benötigte Schlüsselquelle nicht verfügbar; "
                "einen offenen Wechsel nach Behebung fortsetzen."
            ) from None
