"""Schlüsselgenerationen und aktuelle Verweise ohne Datenänderung berichten."""

import json

from django.core.management.base import BaseCommand

from core.keyinventory import KeyInventory
from core.keyrotation import rotation_lock
from core.tenancy import rls_bypass


class Command(BaseCommand):
    help = "Lesender JSON-Bericht über Schlüsselgenerationen, aktuelle Verweise und Prüfsperren."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", type=int, required=True)

    def handle(self, *args, organisation, **options):
        with rotation_lock(), rls_bypass():
            self.stdout.write(
                json.dumps(KeyInventory(organisation).read(), default=str, sort_keys=True)
            )
