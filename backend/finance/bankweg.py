"""Bankweg: die austauschbare Schicht zwischen Kasse und Bank.

Ein Bankweg holt Umsätze direkt bei der Bank (später auch: reicht Lastschriften und
Überweisungen ein). Der erste Weg ist FinTS (``fints_weg.py``); EBICS oder ein lizenzierter
Kontoinformationsdienst können später als weitere Wege dazukommen, ohne dass sich
Kontoauszüge, Vorschläge oder Oberfläche ändern.

Ein Vorgang besteht aus Schritten. Jeder Schritt bekommt das Geheimnis des Nutzers (bei
FinTS die PIN) neu mit; gespeichert wird es nie. Verlangt die Bank eine Freigabe (TAN),
endet der Schritt mit ``Step.tan`` und dem angehaltenen Dialog; der nächste Schritt setzt
ihn fort.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import gettext


class BankError(Exception):
    """Fehler eines Bankwegs. ``code``: pin, locked, connection, unsupported, bank, expired."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Step:
    """Ergebnis eines Schritts: fertig (``result``) oder Freigabe nötig (``dialog``)."""

    done: bool
    result: dict = field(default_factory=dict)
    # Freigabe: Text der Bank, ohne Eintippen (App) oder mit TAN, optional ein Bild (photoTAN)
    challenge: str = ""
    decoupled: bool = False
    image: str = ""  # data:-URL
    # angehaltener Dialog; wird verschlüsselt abgelegt und beim nächsten Schritt mitgegeben
    dialog: dict | None = None
    # neuer Sitzungsstand des Zugangs (z. B. Kundensystem-ID), verschlüsselt zu speichern
    state: str | None = None


class Bankweg:
    key = ""
    label = ""

    def available(self) -> bool:
        raise NotImplementedError

    def start(self, access, secret: str, job: dict) -> Step:
        raise NotImplementedError

    def resume(self, access, secret: str, dialog: dict, tan: str) -> Step:
        raise NotImplementedError


def fints_available() -> bool:
    return bool(settings.FINTS_ENABLED and settings.FINTS_PRODUCT_ID)


def get(key: str) -> Bankweg:
    if key == "fints":
        from .fints_weg import FinTSWeg

        return FinTSWeg()
    raise BankError("unsupported", gettext("Unbekannter Bankweg."))


def available_ways() -> list[str]:
    return ["fints"] if fints_available() else []
