"""Gesamtaudit 10.11.2026: Regressionstests zu einzelnen Befunden (erfundene Daten)."""

from email.message import EmailMessage

import pytest

from circulars import inbound
from finance import camt

# --- V01: Ein „dmarc=pass“ im Kommentar oder in fremdem Text zählt nicht ---


@pytest.mark.parametrize(
    "header, passed",
    [
        ("mx.example.org; dmarc=pass header.from=example.org", True),
        ("mx.example.org 1; spf=pass;\n\tdkim=pass;\n\tDMARC = Pass (p=none)", True),
        ("mx.example.org (Kommentar); dmarc=pass", True),
        ("mx.example.org; spf=pass (fremder Text dmarc=pass)", False),
        ("mx.example.org; spf=pass (a (b) dmarc=pass); dkim=none", False),
        ('mx.example.org; spf=pass reason="x; dmarc=pass"', False),
        ("mx.example.org; spf=pass smtp.mailfrom=dmarc=pass", False),
        ("mx.example.org; dmarc=pass; dmarc=fail", False),
        ("mx.example.org; dmarc=passed", False),
        ("mx.example.org.fremd; dmarc=pass", False),
    ],
)
def test_dmarc_nur_echtes_ergebnis(settings, header, passed):
    settings.MAIL_AUTHSERV_ID = "mx.example.org"
    msg = EmailMessage()
    msg["Authentication-Results"] = header
    assert inbound.dmarc_passed(msg) is passed


# --- F01: Extremwerte im CAMT-Betrag sind ein Prüffehler, kein interner Fehler ---


@pytest.mark.parametrize(
    "raw", ["1E100", "-1E100", "1E-100", "NaN", "Infinity", "12.345", "10000000000.00", "x"]
)
def test_camt_betrag_extremwerte(raw):
    with pytest.raises(camt.CamtError):
        camt._amount(raw, signed=True)


def test_camt_betrag_grenzwert():
    assert str(camt._amount("9999999999.99")) == "9999999999.99"
    assert str(camt._amount("12.3")) == "12.3"
