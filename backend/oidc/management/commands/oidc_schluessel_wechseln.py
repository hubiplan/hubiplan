"""Schlüssel der Anmeldebestätigungen (ID-Token) wechseln, ohne Unterbrechung.

Ablauf (docs/nextcloud.md): erst wechseln, dann warten, bis die angebundenen Dienste die
Schlüsselliste neu geholt haben (mindestens ein Tag), dann mit ``--alten-entfernen`` den
vorherigen Schlüssel aus der Liste nehmen.
"""

from django.core.management.base import BaseCommand

from oidc import keys


class Command(BaseCommand):
    help = "Legt einen neuen OIDC-Schlüssel an; der bisherige bleibt in der Schlüsselliste."

    def add_arguments(self, parser):
        parser.add_argument(
            "--alten-entfernen",
            action="store_true",
            help="Nur den vorherigen Schlüssel aus der Liste nehmen, keinen neuen anlegen.",
        )

    def handle(self, *args, **options):
        if options["alten_entfernen"]:
            if keys.drop_previous():
                self.stdout.write("Vorheriger Schlüssel entfernt.")
            else:
                self.stdout.write("Es gibt keinen vorherigen Schlüssel.")
            return
        new, old = keys.rotate()
        self.stdout.write(
            f"Neuer Schlüssel {new}; der bisherige ({old}) bleibt in der Schlüsselliste, "
            "bis er mit --alten-entfernen herausgenommen wird."
        )
