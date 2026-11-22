#!/usr/bin/env python3
"""Erzeugt symbole.json fuer beide Apps (Android, iOS) aus einfachen SVG-Formen.

Raster 24 x 24, Strich 1,75, runde Enden. Ausgabe je Symbol: Teilpfade nur mit den
Befehlen M, L, C, Z in absoluten Koordinaten, damit beide Apps denselben kleinen Leser nutzen.
Aufruf: python3 scripts/app-symbole.py > symbole.json   (braucht fonttools)
Die Datei gehoert danach unveraendert in beide Apps, siehe docs/app-gestaltung.md.
"""
import json
import sys

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path


def kreis(cx, cy, r):
    return f"M{cx - r} {cy}a{r} {r} 0 1 0 {2 * r} 0a{r} {r} 0 1 0 {-2 * r} 0z"


def rechteck(x, y, w, h, r=0):
    if r == 0:
        return f"M{x} {y}h{w}v{h}h{-w}z"
    return (
        f"M{x + r} {y}h{w - 2 * r}a{r} {r} 0 0 1 {r} {r}v{h - 2 * r}a{r} {r} 0 0 1 {-r} {r}"
        f"h{-(w - 2 * r)}a{r} {r} 0 0 1 {-r} {-r}v{-(h - 2 * r)}a{r} {r} 0 0 1 {r} {-r}z"
    )


K, R = kreis, rechteck

# name: (Strichpfade, Flaechenpfade)
SYMBOLE = {
    # Reiter
    "start": (["M3 10.5 12 3l9 7.5", "M5 9.5V21h14V9.5", "M10 21v-6h4v6"], []),
    "termine": ([R(3.5, 5, 17, 15.5, 2), "M3.5 10h17", "M8 3v4", "M16 3v4"], []),
    "neues": (["M4 5h16v11H9l-5 4z", "M8 9h8", "M8 12.5h5"], []),
    "ich": ([K(12, 8.5, 4), "M4 21c1.2-4 4.3-6 8-6s6.8 2 8 6"], []),
    "verwaltung": ([R(3.5, 7, 17, 13, 2), "M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2", "M3.5 12.5h17"], []),
    "noten": (["M9 18V5l11-2v13", K(6.5, 18, 2.5), K(17.5, 16, 2.5)], []),
    "aufgaben": (["M9 6h11", "M9 12h11", "M9 18h11", "m3.5 6 1 1 2-2", "m3.5 12 1 1 2-2", "m3.5 18 1 1 2-2"], []),
    # Mitglied
    "ausweis": ([R(3, 5, 18, 14, 2), K(8.5, 11, 2), "M5.5 16c.6-1.5 1.7-2.2 3-2.2s2.4.7 3 2.2", "M14 10h4", "M14 13.5h3"], []),
    "einchecken": ([K(12, 12, 8.5), "m8.5 12.3 2.4 2.4 4.6-4.9"], []),
    "kalender-abo": ([R(3.5, 5, 17, 15.5, 2), "M3.5 10h17", "M12 13v5", "M9.5 15.5h5"], []),
    "geld": (["M17.5 6.5a6.5 6.5 0 1 0 0 11", "M4.5 10.5h9", "M4.5 13.5h8"], []),
    "rechnung": (["M6 3h12v18l-3-2-3 2-3-2-3 2z", "M9 8h6", "M9 11.5h6", "M9 15h3"], []),
    "nachweis": (["M6 3h8l4 4v14H6z", "M14 3v4h4", "m9 14.5 2 2 4-4.3"], []),
    "bestellung": (["M5 8h14l-1 13H6z", "M9 8V6.5a3 3 0 0 1 6 0V8"], []),
    "training": ([K(12, 12, 8.5), K(12, 12, 4.5)], [K(12, 12, 1.2)]),
    "wettbewerb": (["M8 4h8v5a4 4 0 0 1-8 0z", "M8 5.5H5v1.5a3 3 0 0 0 3 3", "M16 5.5h3v1.5a3 3 0 0 1-3 3", "M12 13v4", "M8.5 20.5h7", "M9.5 17h5v3.5h-5z"], []),
    "helfer": ([K(9, 8.5, 3.5), "M2.5 20c.9-3.4 3.4-5 6.5-5s5.6 1.6 6.5 5", "M16 5.2a3.5 3.5 0 0 1 0 6.6", "M18 15.3c1.7.7 2.9 2.2 3.5 4.7"], []),
    "abwesenheit": ([R(3.5, 5, 17, 15.5, 2), "M3.5 10h17", "M8 3v4", "M16 3v4", "m9.5 13 5 5", "m14.5 13-5 5"], []),
    "belegung": (["M4 21V8l8-5 8 5v13", "M9.5 21v-6h5v6", "M9 10.5h6"], []),
    "versammlung": ([K(12, 7, 3), "M6.5 20c.6-3.6 2.7-5.5 5.5-5.5s4.9 1.9 5.5 5.5", K(4.8, 10, 2), K(19.2, 10, 2), "M1.5 18.5c.3-2 1.3-3.4 3-3.9", "M22.5 18.5c-.3-2-1.3-3.4-3-3.9"], []),
    "dokument": (["M6 3h8l4 4v14H6z", "M14 3v4h4", "M9 12h6", "M9 15.5h6"], []),
    "ordner": (["M3.5 6.5h6l2 2.5h9v10.5h-17z"], []),
    "meine-daten": ([K(12, 12, 9), K(12, 10, 3), "M6.5 18.2c1.3-2 3.2-3 5.5-3s4.2 1 5.5 3"], []),
    "pinnwand": (["M9 3.5h6l-1 6 3 3.5H7l3-3.5z", "M12 13v7.5"], []),
    "umfrage": (["M4 20.5h16", "M7 20.5v-7", "M12 20.5v-13", "M17 20.5v-10"], []),
    "mitteilung": ([R(3, 5.5, 18, 13, 2), "m3.5 7 8.5 6.5L20.5 7"], []),
    "firma": (["M4 21V5h10v16", "M14 10h6v11", "M7.5 9h3", "M7.5 13h3", "M7.5 17h3", "M2.5 21h19"], []),
    # Verwaltung
    "mitglieder": ([K(9, 8.5, 3.5), "M2.5 20c.9-3.4 3.4-5 6.5-5s5.6 1.6 6.5 5", "M16 5.2a3.5 3.5 0 0 1 0 6.6", "M18 15.3c1.7.7 2.9 2.2 3.5 4.7"], []),
    "antrag": ([K(10, 8.5, 3.5), "M3.5 20c.9-3.4 3.4-5 6.5-5 1.5 0 2.900.400 4 1.100", "M18.5 13.500v6", "M15.500 16.500h6"], []),
    "jubilaeum": ([R(4, 10, 16, 10.500, 1.500), "M3 10h18", "M12 10v10.500", "M12 10c-1.500-4-5.500-4.500-5.500-2 0 1.500 2 2 5.500 2z", "M12 10c1.500-4 5.500-4.500 5.500-2 0 1.500-2 2-5.500 2z"], []),
    "qualifikation": ([K(12, 9.500, 5.500), "m8.500 14 -1.500 7 5-2.500 5 2.500-1.500-7", "m9.800 9.600 1.600 1.600 2.900-3"], []),
    "frist": (["M7 3.500h10", "M7 20.500h10", "M8 3.500c0 5 8 5.500 8 8.500s-8 3.500-8 8.500", "M16 3.500c0 5-8 5.500-8 8.500s8 3.500 8 8.500"], []),
    "partner": ([R(3.500, 7, 17, 13, 2), "M9 7V5a1.500 1.500 0 0 1 1.500-1.500h3A1.500 1.500 0 0 1 15 5v2", "M3.500 12.500h17", "M12 11.500v2.500"], []),
    "kassenbuch": (["M6 3h12v18H6z", "M9.500 3v8l2-1.500 2 1.500V3", "M9 15.500h6"], []),
    "einlass": (["M3.500 8.500h17v2.500a1.500 1.500 0 0 0 0 3v2.500h-17v-2.500a1.500 1.500 0 0 0 0-3z", "M14.500 8.500v8"], []),
    "zu-erledigen": (["M4 5h16v14H4z", "M4 14h4.500a3.500 3.500 0 0 0 7 0H20"], []),
    # Handlungen
    "plus": (["M12 5v14", "M5 12h14"], []),
    "suche": ([K(11, 11, 6.500), "m16 16 4.500 4.500"], []),
    "kamera": (["M4 8h3l2-3h6l2 3h3v11H4z", K(12, 13, 3.500)], []),
    "scannen": (["M4 8V5.500A1.500 1.500 0 0 1 5.500 4H8", "M16 4h2.500A1.500 1.500 0 0 1 20 5.500V8", "M20 16v2.500a1.500 1.500 0 0 1-1.500 1.500H16", "M8 20H5.500A1.500 1.500 0 0 1 4 18.500V16", "M4 12h16"], []),
    "hilfe": ([K(12, 12, 9), "M9.600 9.300a2.500 2.500 0 0 1 4.800.900c0 1.700-2.400 2.100-2.400 3.600"], [K(12, 17, 0.900)]),
    "wallet": ([R(3.500, 6, 17, 13, 2), "M15 12.500h5.500", "M3.500 9.500h17"], []),
    "helligkeit": ([K(12, 12, 4), "M12 2.500v2", "M12 19.500v2", "M2.500 12h2", "M19.500 12h2", "m5.300 5.300 1.400 1.400", "m17.300 17.300 1.400 1.400", "m5.300 18.700 1.400-1.400", "m17.300 6.700 1.400-1.400"], []),
    "ort": (["M12 21s-6.500-5.600-6.500-11a6.500 6.500 0 0 1 13 0c0 5.400-6.500 11-6.500 11z", K(12, 10, 2.300)], []),
    "uhr": ([K(12, 12, 8.500), "M12 7.500V12l3 2"], []),
    "telefon": (["M6.500 3.500h3l1.500 4-2 1.500c1 2.500 3 4.500 5.500 5.500l1.500-2 4 1.500v3c0 1-1 2-2.500 2C10.500 19 5 13.500 4.500 6c0-1.500 1-2.500 2-2.500z"], []),
    "teilen": ([K(6.500, 12, 2.500), K(17.500, 5.500, 2.500), K(17.500, 18.500, 2.500), "m8.700 10.800 6.600-4", "m8.700 13.200 6.600 4"], []),
    "einstellungen": (["M4 7h9", "M17 7h3", "M4 17h3", "M11 17h9", K(15, 7, 2), K(9, 17, 2)], []),
    "sperre": ([R(5, 10.500, 14, 10, 2), "M8 10.500V8a4 4 0 0 1 8 0v2.500"], [K(12, 15.500, 1.100)]),
    "offline": (["M7 18.500h9.500a4 4 0 0 0 1.300-7.800A6 6 0 0 0 8.500 7.500", "M6.300 9.800A4.500 4.500 0 0 0 7 18.500", "M4 4l16 16"], []),
    "weiter": (["m9 5 7 7-7 7"], []),
    "zurueck": (["M15 5 8 12l7 7"], []),
    "unten": (["m6 9 6 6 6-6"], []),
    "haken": (["m5 12.500 4.500 4.500L19 7.500"], []),
    "schliessen": (["M6 6l12 12", "M18 6 6 18"], []),
    "info": ([K(12, 12, 9), "M12 11v6"], [K(12, 7.700, 1)]),
    "warnung": (["M12 3.500 22 20.500H2z", "M12 10v5"], [K(12, 17.700, 0.900)]),
    "konto": ([K(12, 12, 9), K(12, 10, 3), "M6.500 18.200c1.300-2 3.200-3 5.500-3s4.200 1 5.500 3"], []),
}


def zahl(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def flach(d):
    """SVG-Pfad -> Liste von Teilpfaden, nur M/L/C/Z absolut."""
    pen = RecordingPen()
    parse_path(d, pen)
    teile, akt, pos = [], [], (0.0, 0.0)
    for op, args in pen.value:
        if op == "moveTo":
            if akt:
                teile.append(" ".join(akt))
            pos = args[0]
            akt = [f"M {zahl(pos[0])} {zahl(pos[1])}"]
        elif op == "lineTo":
            pos = args[0]
            akt.append(f"L {zahl(pos[0])} {zahl(pos[1])}")
        elif op == "curveTo":
            (a, b, c) = args
            akt.append("C " + " ".join(zahl(v) for p in (a, b, c) for v in p))
            pos = c
        elif op == "qCurveTo":
            assert len(args) == 2, d
            q, e = args
            a = (pos[0] + 2 / 3 * (q[0] - pos[0]), pos[1] + 2 / 3 * (q[1] - pos[1]))
            b = (e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1]))
            akt.append("C " + " ".join(zahl(v) for p in (a, b, e) for v in p))
            pos = e
        elif op == "closePath":
            akt.append("Z")
        elif op == "endPath":
            pass
        else:
            raise ValueError(op)
    if akt:
        teile.append(" ".join(akt))
    return teile


def main():
    aus = {}
    for name, (strich, flaeche) in sorted(SYMBOLE.items()):
        aus[name] = {
            "strich": [t for d in strich for t in flach(d)],
            "flaeche": [t for d in flaeche for t in flach(d)],
        }
    json.dump({"raster": 24, "strich": 1.75, "symbole": aus}, sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
