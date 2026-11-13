"""Prüfung von Personennamen aus Formularen ohne Anmeldung.

Solche Namen stehen in Mails an Adressen, die noch niemand bestätigt hat. Frei wählbarer Text
darin wäre ein Weg, im Namen des Vereins Werbung oder Köder zu verschicken (Gesamtaudit 13.11.
S-01, H-09). Erlaubt ist deshalb nur, was in Namen vorkommt.
"""

from __future__ import annotations

import re

# je Namensteil: Buchstaben, Bindestrich, Apostroph, am Ende ein Punkt („Dr.“, „jun.“)
_PART = re.compile(r"^[^\W\d_](?:[^\W\d_]|['’-])*\.?$")
_LINK = re.compile(r"(?i)(://|www\.|https?:)")


def clean_person_name(value: str) -> str | None:
    """Name mit einfachen Leerzeichen, oder None, wenn er nicht wie ein Name aussieht."""
    value = " ".join((value or "").split())
    if not value or not all(_PART.match(part) for part in value.split(" ")):
        return None
    return value


def has_link(value: str) -> bool:
    """Steht in einem freien Namen (z. B. einer Organisation) eine Webadresse?"""
    return bool(_LINK.search(value or ""))
