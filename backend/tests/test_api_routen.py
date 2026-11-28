"""Die eingecheckte Adressliste ``config/api_routen.json`` passt zum Code.

Die Web-Oberfläche prüft gegen diese Liste, dass es jede Adresse gibt, die sie aufruft
(``frontend/src/test/ApiAdressen.test.ts``). Deshalb muss die Liste aktuell sein.
"""

import re
from pathlib import Path

from core.management.commands.api_routen import routen, text

KOPIE = Path(__file__).resolve().parent.parent / "config" / "api_routen.json"


def test_adressliste_ist_aktuell():
    assert KOPIE.read_text(encoding="utf-8") == text(), (
        "config/api_routen.json ist veraltet: im Ordner backend "
        "„python manage.py api_routen config/api_routen.json“ ausführen"
    )


def test_muster_sind_gueltig_und_ohne_benannte_gruppen():
    muster = routen()
    assert len(muster) > 500
    for m in muster:
        assert "(?P<" not in m and r"\Z" not in m
        re.compile(m)
    assert any(re.match(m, "api/orgs/1/member-types/") for m in muster)
