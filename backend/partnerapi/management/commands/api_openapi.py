"""``manage.py api_openapi [Datei]``: OpenAPI-Beschreibung der API für andere Programme.

Ohne Datei auf die Standardausgabe. Die Kopie ``partnerapi/openapi.json`` wird damit erzeugt;
``tests/test_partnerapi.py`` meldet, wenn sie nicht mehr zum Code passt.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from partnerapi import openapi


def text() -> str:
    return json.dumps(openapi.build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


class Command(BaseCommand):
    help = "OpenAPI-Beschreibung der API für andere Programme ausgeben (docs/api.md)"

    def add_arguments(self, parser):
        parser.add_argument("datei", nargs="?", help="Zieldatei (sonst Standardausgabe)")

    def handle(self, *args, datei=None, **options):
        if datei:
            Path(datei).write_text(text(), encoding="utf-8")
        else:
            self.stdout.write(text(), ending="")
