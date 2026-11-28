"""Wächter für die Architekturregeln (docs/architektur.md).

Der heutige Stand steht in ``tests/data/architektur_stand.json``. Neuer Code darf ihn nicht
verschlechtern; wer ihn verbessert, schreibt den Bestand neu
(``python tests/architektur.py --schreiben``), damit die Verbesserung hält.
"""

from . import architektur

NEU_SCHREIBEN = "Bestand neu schreiben: python tests/architektur.py --schreiben"


def test_adressen_liegen_nicht_im_kern():
    """Die Adressen aller Bereiche bindet ``config`` ein, nicht ``core``: Sonst hängt der
    Kern an jedem Fachmodul."""
    assert not (architektur.BACKEND / "core" / "urls.py").exists()


def test_keine_neuen_importe_gegen_die_schichtrichtung():
    erlaubt = set(architektur.bestand()["rueckwaerts"])
    neu = sorted(set(architektur.rueckwaerts()) - erlaubt)
    assert not neu, (
        "Neue Importe gegen die Schichtrichtung (Kern < Grundlagen < Fachmodule < "
        f"Zusammenführung, siehe docs/architektur.md): {neu}"
    )


def test_bestand_der_rueckwaertsimporte_ist_aktuell():
    erledigt = sorted(set(architektur.bestand()["rueckwaerts"]) - set(architektur.rueckwaerts()))
    assert not erledigt, f"Diese Importe gibt es nicht mehr. {NEU_SCHREIBEN} ({erledigt})"
