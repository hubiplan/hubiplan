"""Die Antworten für den Feldabgleich mit der Web-Oberfläche sind aktuell.

Schlägt ``test_antworten_sind_aktuell`` fehl, liefert der Server in diesem Bereich ein Feld
neu, nicht mehr oder in anderer Art. Dann die Antworten neu schreiben, daraus die Konstanten der
Oberfläche erzeugen und deren Typen anpassen, bis ``npm run typecheck`` wieder grün ist::

    FELDABGLEICH_SCHREIBEN=1 pytest tests/test_feldabgleich.py      (im Ordner backend)
    node scripts/feldabgleich.mjs && npm run typecheck              (im Ordner frontend)

Dass die Konstanten der Oberfläche zu den Antworten passen, prüft dort
``src/test/Feldabgleich.test.ts``.
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
        datei.write_text(fa.als_json(bereich, daten), encoding="utf-8")
    alt = fa.aus_json(datei.read_text(encoding="utf-8"))
    assert fa.formen(alt) == fa.formen(daten), (
        f"backend/config/feldabgleich/{bereich}.json ist veraltet (siehe Kopf dieses Tests)"
    )


@pytest.mark.parametrize("bereich", sorted(fa.BEREICHE))
def test_kein_feld_ohne_beispiel(bereich):
    """Ein Feld, das immer leer bleibt, prüft die Oberfläche nicht: Beispiel ergänzen
    (``tests/feldabgleich_<bereich>.py``) oder mit Grund in ``OHNE_BEISPIEL`` eintragen."""
    daten = fa.aus_json((fa.ZIEL / f"{bereich}.json").read_text(encoding="utf-8"))
    assert set(fa.luecken(daten)) == set(fa.OHNE_BEISPIEL[bereich])
