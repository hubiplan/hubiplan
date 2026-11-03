"""Bestandslauf mit festem, geprüftem Umfang statt pauschaler Feldauswahl."""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.namecopies import FIELDS


class Command(BaseCommand):
    help = "Inventarisierte Namenskopien verschlüsseln oder mit --pruefen streng prüfen."

    def add_arguments(self, parser):
        parser.add_argument("--pruefen", action="store_true")
        parser.add_argument("--probe", action="store_true")

    def handle(self, *args, pruefen=False, probe=False, **options):
        fields = [f"{model}.{field}" for model, names in FIELDS.items() for field in names]
        call_command(
            "daten_verschluesseln",
            feld=fields,
            pruefen=pruefen,
            probe=probe,
            stdout=self.stdout,
            stderr=self.stderr,
        )
