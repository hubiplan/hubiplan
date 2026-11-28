"""Die eingecheckte Form der öffentlichen Webseiten-Schnittstelle passt zum Code, und die
Beispielvereine belegen jedes Feld.

Schlägt ``test_form_ist_aktuell`` fehl, hat sich eine Antwort unter ``/api/public/site/v1/``
geändert (Feld neu, entfernt oder von anderer Art). Dann beide Dateien neu schreiben und in
der Vereinswebseite die Kopien nachziehen (dort ``scripts/schnittstelle.sh``)::

    WEBSEITE_SCHNITTSTELLE_SCHREIBEN=1 pytest tests/test_webseite_form.py

Schlägt ``test_kein_feld_ohne_beispiel`` fehl, liefert die Schnittstelle ein Feld, das kein
Beispielverein belegt: in ``tests/webseite_pruefverein.py`` ergänzen.
"""

import json
import os
import re

import pytest
from django.urls import get_resolver

from website import home

from . import webseite_form as ws

pytestmark = [pytest.mark.django_db, pytest.mark.langsam]


@pytest.fixture
def abrufe():
    return ws.alle_abrufe()


def test_form_ist_aktuell(abrufe):
    daten = ws.formen(abrufe)
    if os.environ.get("WEBSEITE_SCHNITTSTELLE_SCHREIBEN"):
        ws.DATEI.write_text(ws.text(daten), encoding="utf-8")
        ws.ANTWORTEN.write_text(ws.text(ws.aufzeichnung(abrufe)), encoding="utf-8")
    assert json.loads(ws.DATEI.read_text(encoding="utf-8")) == daten, (
        "config/webseite_schnittstelle.json ist veraltet (siehe Kopf dieses Tests)"
    )


def test_kein_feld_ohne_beispiel(abrufe):
    luecken = ws.luecken(ws.formen(abrufe))
    assert luecken == [], "\n".join(luecken)


def test_jede_abschnittsart_kommt_vor(abrufe):
    assert set(home.ALL_KINDS) - ws.arten_der_abschnitte(abrufe) == set()


def test_eingecheckte_antworten_haben_die_eingecheckte_form():
    """Die Aufzeichnung für die Webseite ist so aktuell wie die Form."""
    aufzeichnung = json.loads(ws.ANTWORTEN.read_text(encoding="utf-8"))["antworten"]
    abrufe = [(e["beispiel"], e["adresse"], e["pfad"], e["antwort"]) for e in aufzeichnung]
    assert ws.formen(abrufe) == json.loads(ws.DATEI.read_text(encoding="utf-8"))


def test_jede_adresse_ist_eingeordnet():
    """Neue Adresse der Schnittstelle: mit Feldern nach ``ALLE`` (und in ``abrufe``
    aufnehmen), ohne Felder nach ``OHNE_FELDER``."""
    gefunden = set()

    def lauf(muster, vor=""):
        for eintrag in muster:
            pfad = vor + str(eintrag.pattern)
            if hasattr(eintrag, "url_patterns"):
                lauf(eintrag.url_patterns, pfad)
            elif "public/site/v1/" in pfad:
                gefunden.add(pfad.split("public/site/v1/", 1)[1])

    lauf(get_resolver().url_patterns)
    namen = {re.sub(r"<(?:\w+:)?(\w+)>", r"<\1>", pfad) for pfad in gefunden}
    namen = {n.removeprefix("<key>/") for n in namen}
    bekannt = {re.sub(r"<\w+>", "<>", n) for n in (*ws.ALLE, *ws.OHNE_FELDER)}
    assert {n for n in namen if re.sub(r"<\w+>", "<>", n) not in bekannt} == set()


def test_form_vereint_felder_und_arten():
    a = ws.form([{"a": 1, "b": None}, {"a": "x"}])
    assert a == [{"a": "text|zahl", "b": "fehlt|null"}]
    assert ws.form({"liste": [], "an": True}) == {"an": "bool", "liste": []}
    # Objekt oder null, Liste oder fehlend: einfache Arten unter „?“, Liste unter „?liste“
    assert ws.vereinen({"x": "text"}, "null") == {"x": "text", "?": "null"}
    assert ws.vereinen(["text"], "fehlt") == {"?": "fehlt", "?liste": ["text"]}
    assert ws.vereinen(ws.vereinen(["text"], "fehlt"), ["zahl"]) == {
        "?": "fehlt",
        "?liste": ["text|zahl"],
    }
