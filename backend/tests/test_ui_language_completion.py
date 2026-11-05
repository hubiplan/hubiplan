"""Dynamische Systemtexte; fachliche Daten und Finanzexport bleiben deutsch."""

import pytest
from django.utils import translation

from billing.models import Payment
from circulars.models import Circular
from core.i18n import german
from finance.models import Account, CashReceipt


@pytest.mark.parametrize(
    "value,de,en",
    [
        (Account.Kind.CASH, "Barkasse", "Cash box"),
        (Payment.Method.CASH, "bar", "cash"),
        (Circular.Status.SENT, "abgearbeitet", "processed"),
    ],
)
def test_auswahltexte_werden_zur_aktuellen_sprache_aufgeloest(value, de, en):
    with translation.override("de"):
        assert str(value.label) == de
    with translation.override("en"):
        assert str(value.label) == en
        assert german(value.label) == de


def test_quittungsfehler_nennen_fehlende_angaben_auf_englisch():
    from finance.quittung import missing

    receipt = CashReceipt(direction="in")
    with translation.override("en"):
        assert missing(receipt) == ["Treasurer’s signature", "Payer’s signature"]
    with translation.override("de"):
        assert missing(receipt) == ["Unterschrift des Kassierers", "Unterschrift des Zahlers"]
