"""Die Antworten für den Feldabgleich mit der Web-Oberfläche sind aktuell.

Schlägt ``test_antworten_sind_aktuell`` fehl, liefert der Server in diesem Bereich ein Feld
neu, nicht mehr oder in anderer Art. Dann die Dateien neu schreiben und die Typen der
Oberfläche anpassen, bis ``npm run typecheck`` im Ordner ``frontend`` wieder grün ist::

    FELDABGLEICH_SCHREIBEN=1 pytest tests/test_feldabgleich.py
"""

import os

import pytest

from . import feldabgleich as fa

pytestmark = [pytest.mark.django_db, pytest.mark.langsam]


@pytest.mark.parametrize("bereich", sorted(fa.BEREICHE))
def test_antworten_sind_aktuell(bereich):
    daten = fa.BEREICHE[bereich][1]()
    datei = fa.ZIEL / f"{bereich}.json"
    if os.environ.get("FELDABGLEICH_SCHREIBEN"):
        fa.ZIEL.mkdir(parents=True, exist_ok=True)
        datei.write_text(fa.als_json(daten), encoding="utf-8")
        (fa.ZIEL / f"{bereich}.ts").write_text(fa.als_typescript(bereich, daten), encoding="utf-8")
    alt = fa.aus_json(datei.read_text(encoding="utf-8"))
    assert fa.formen(alt) == fa.formen(daten), (
        f"frontend/src/test/feldabgleich/{bereich}.json ist veraltet (siehe Kopf dieses Tests)"
    )


@pytest.mark.parametrize("bereich", sorted(fa.BEREICHE))
def test_kein_feld_ohne_beispiel(bereich):
    """Ein Feld, das immer leer bleibt, prüft die Oberfläche nicht: Beispiel ergänzen
    (``tests/feldabgleich_<bereich>.py``) oder mit Grund in ``OHNE_BEISPIEL`` eintragen."""
    daten = fa.aus_json((fa.ZIEL / f"{bereich}.json").read_text(encoding="utf-8"))
    assert set(fa.luecken(daten)) == set(fa.OHNE_BEISPIEL[bereich])


@pytest.mark.parametrize("bereich", sorted(fa.BEREICHE))
def test_typescript_passt_zu_den_daten(bereich):
    daten = fa.aus_json((fa.ZIEL / f"{bereich}.json").read_text(encoding="utf-8"))
    erzeugt = (fa.ZIEL / f"{bereich}.ts").read_text(encoding="utf-8")
    assert erzeugt == fa.als_typescript(bereich, daten)
