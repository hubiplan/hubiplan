"""Breite Logos (Schriftzüge) in PDFs (#527): Höhe fest, Breite nach dem Seitenverhältnis bis
zu einer Obergrenze; quadratische Wappen wie bisher."""

import io

from PIL import Image

from core.logobox import logo_size


def _png(w: int, h: int) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "#123456").save(buf, "PNG")
    buf.seek(0)
    return buf


def _rund(groesse: tuple[float, float]) -> tuple[float, float]:
    return round(groesse[0], 6), round(groesse[1], 6)


def test_quadrat_bleibt_quadrat():
    assert _rund(logo_size(_png(200, 200), 55, 18)) == (18, 18)


def test_schriftzug_wird_breiter_statt_kleiner():
    assert _rund(logo_size(_png(300, 100), 55, 18)) == (54, 18)


def test_obergrenze_der_breite():
    assert _rund(logo_size(_png(1000, 100), 55, 18)) == (55, 5.5)


def test_hochformat_passt_in_die_hoehe():
    assert _rund(logo_size(_png(100, 200), 55, 18)) == (9, 18)


def test_unlesbares_bild_wie_bisher_quadrat():
    assert logo_size(io.BytesIO(b"kein Bild"), 24, 8) == (8, 8)
