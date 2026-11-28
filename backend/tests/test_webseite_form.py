"""Die eingecheckte Form der öffentlichen Webseiten-Schnittstelle passt zum Code.

Schlägt der Test fehl, hat sich eine Antwort unter ``/api/public/site/v1/`` geändert (Feld
neu, entfernt oder von anderer Art). Dann die Datei neu schreiben und in der Vereinswebseite
die Kopie nachziehen::

    WEBSEITE_SCHNITTSTELLE_SCHREIBEN=1 pytest tests/test_webseite_form.py
"""

import json
import os

import pytest

from . import webseite_form as ws

pytestmark = [pytest.mark.django_db, pytest.mark.langsam]


def test_form_ist_aktuell():
    daten = ws.formen(ws.demoverein())
    if os.environ.get("WEBSEITE_SCHNITTSTELLE_SCHREIBEN"):
        ws.DATEI.write_text(ws.text(daten), encoding="utf-8")
    assert json.loads(ws.DATEI.read_text(encoding="utf-8")) == daten, (
        "config/webseite_schnittstelle.json ist veraltet (siehe Kopf dieses Tests)"
    )


def test_form_vereint_felder_und_arten():
    a = ws.form([{"a": 1, "b": None}, {"a": "x"}])
    assert a == [{"a": "text|zahl", "b": "fehlt|null"}]
    assert ws.form({"liste": [], "an": True}) == {"an": "bool", "liste": []}
