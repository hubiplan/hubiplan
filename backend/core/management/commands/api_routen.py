"""``manage.py api_routen [Datei]``: die Adressen der Schnittstelle als Liste von Mustern.

Ohne Datei auf die Standardausgabe. Die Kopie ``config/api_routen.json`` wird damit erzeugt;
``tests/test_api_routen.py`` meldet, wenn sie nicht mehr zum Code passt. Die Web-Oberfläche
prüft gegen diese Liste, dass es jede Adresse gibt, die sie aufruft
(``frontend/src/test/ApiAdressen.test.ts``, docs/architektur.md).

Eine JSON-Liste; je Eintrag ein regulärer Ausdruck für den Pfad ohne führenden Schrägstrich,
in einer Form, die Python und JavaScript gleich lesen (Gruppen ohne Namen, Ende als ``$``).
Enthalten ist, was unter ``api/`` und ``_allauth/`` liegt; Admin und Mediendateien hängen von
Einstellungen ab und gehören nicht dazu.
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver

BEREICHE = ("api/", "_allauth/")
_NAME = re.compile(r"\(\?P<\w+>")


def _teil(pattern) -> str:
    return pattern.regex.pattern.removeprefix("^")


def _muster(resolver, davor=""):
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _muster(p, davor + _teil(p.pattern))
        elif isinstance(p, URLPattern):
            yield davor + _teil(p.pattern)


def routen() -> list[str]:
    """Muster aller Adressen, sortiert und ohne Doppelte."""
    return sorted(
        {
            "^" + _NAME.sub("(", m).replace(r"\Z", "$")
            for m in _muster(get_resolver())
            if m.startswith(BEREICHE)
        }
    )


def text() -> str:
    return json.dumps(routen(), ensure_ascii=False, indent=0) + "\n"


class Command(BaseCommand):
    help = "Muster aller Adressen des Servers ausgeben (config/api_routen.json)"

    def add_arguments(self, parser):
        parser.add_argument("datei", nargs="?", help="Zieldatei (sonst Standardausgabe)")

    def handle(self, *args, datei=None, **options):
        if datei:
            Path(datei).write_text(text(), encoding="utf-8")
        else:
            self.stdout.write(text(), ending="")
