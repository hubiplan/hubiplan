"""Feldabgleich zwischen Server und Web-Oberfläche (docs/architektur.md).

Die Web-Oberfläche beschreibt die Antworten des Servers von Hand als TypeScript-Typen
(``frontend/src/api/*.ts``). Damit beide zusammenpassen, ruft dieser Abgleich je Bereich die
Adressen für den Demoverein ab und hält echte Antworten in
``backend/config/feldabgleich/<bereich>.json`` aktuell. Die Oberfläche erzeugt daraus Daten mit
Typangabe (``frontend/scripts/feldabgleich.mjs``). Ihre Typprüfung (``tsc``) meldet dann jedes Feld, das der Server liefert und der Typ nicht kennt, jedes Pflichtfeld,
das der Server nicht liefert, und jede falsche Art (auch ``null``).

Aufgenommen werden nur so viele Antworten, wie nötig sind, um jede Ausprägung zu zeigen
(jedes Feld, jede Art eines Werts). Die Daten sind die erfundenen des Demovereins.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

from django.core.management import call_command
from django.test import Client

from accounts.models import User
from demodaten import korps
from organizations.models import Organization

from .webseite_form import form, vereinen

# Die Antworten liegen beim Server; die Testumgebung des Servers sieht den Ordner frontend nicht.
ZIEL = Path(__file__).resolve().parents[1] / "config" / "feldabgleich"


@dataclass(frozen=True)
class Abruf:
    """Eine Adresse mit dem Typ ihrer Antwort in der Web-Oberfläche."""

    name: str  # Name der Konstante in der erzeugten Datei
    typ: str  # TypeScript-Typ einer Antwort
    pfade: tuple[str, ...]  # hinter /api/orgs/<id>/


def _demoverein() -> tuple[Organization, Client]:
    call_command("seed_demoverein", password="Test-Passwort-123", stdout=io.StringIO())
    club = Organization.objects.get(name=korps.CLUB_NAME)
    client = Client()
    client.force_login(User.objects.get(email=korps.USERS[0][0]))
    return club, client


def _hole(client: Client, club: Organization, pfad: str):
    antwort = client.get(f"/api/orgs/{club.pk}/{pfad}")
    assert antwort.status_code == 200, f"{pfad}: {antwort.status_code}"
    return antwort.json()


def _auswahl(antworten: list) -> list:
    """Die Antworten, die eine neue Ausprägung zeigen (Feld oder Art eines Werts)."""
    gesamt, out = None, []
    for antwort in antworten:
        neu = form(antwort) if gesamt is None else vereinen(gesamt, form(antwort))
        if neu != gesamt:
            gesamt = neu
            out.append(antwort)
    return out


def _seiten(
    client: Client, club: Organization, pfad: str, abfrage: str = ""
) -> tuple[list[dict], list[int]]:
    """Alle Seiten einer geblätterten Liste als eine Antwort mit den Zeilen, die Neues
    zeigen; dazu die Nummern aller Zeilen."""
    seiten, nummer = [], 1
    while True:
        seite = _hole(client, club, f"{pfad}?page={nummer}&{abfrage}")
        seiten.append(seite)
        if not seite.get("next"):
            break
        nummer += 1
    alle = [zeile for seite in seiten for zeile in seite["results"]]
    # ``previous`` zeigt erst die zweite Seite
    kopf = seiten[min(1, len(seiten) - 1)]
    return [{**seiten[0], "results": _auswahl(alle)}, {**kopf, "results": []}], [
        zeile["id"] for zeile in alle
    ]


def mitglieder() -> dict[str, tuple[str, list]]:
    """Antworten des Bereichs Mitglieder: Name → (Typ, Antworten)."""
    from . import feldabgleich_mitglieder

    club, client = _demoverein()
    _vorher, ids = _seiten(client, club, "members/")
    feldabgleich_mitglieder.fuelle(client, club, ids)
    liste, ids = _seiten(client, club, "members/")
    ehemalige, ids_ehemalige = _seiten(client, club, "members/", "status=ehemalig")
    liste, ids = liste + ehemalige, ids + ids_ehemalige
    return {
        "mitgliedsarten": ("MemberType[]", [_hole(client, club, "member-types/")]),
        "liste": ("Page<MemberRow>", liste),
        "akten": (
            "MemberDetail",
            _auswahl([_hole(client, club, f"members/{pk}/") for pk in ids]),
        ),
        "ansprechpartner": (
            "ContactPerson[]",
            _auswahl([_hole(client, club, f"members/{pk}/contacts/") for pk in ids]),
        ),
    }


# Bereich → (Quelle der Typen in der Oberfläche, Funktion mit den Antworten)
BEREICHE = {
    "mitglieder": ("../../api/members.ts", mitglieder),
}


# Felder, die kein Beispiel belegt, mit Grund. Sie sind in der Oberfläche ungeprüft; die
# Liste darf nur kürzer werden (der Test meldet Einträge, die inzwischen belegt sind).
OHNE_BEISPIEL = {
    "mitglieder": {
        # Meldung an den Dachverband: braucht einen Dachverband mit gemeldeten Mitgliedern
        "akten[].federation": "Dachverband",
        "akten[].duration.federation": "Dachverband",
        "akten[].honorary_titles.federation": "Dachverband",
        "liste[].results[].member_number": "Dachverband",
        # dieselbe Person in einem zweiten Verein desselben Verbands
        "akten[].other_memberships": "Dachverband",
        # Mitglied, das eine verbundene Instanz führt
        "akten[].managed_by": "Verbund zweier Instanzen",
        # nur in der Antwort auf das Vergeben eines Amts (beendete Vorgänger), sonst leer
        "akten[].department_roles[].ended": "nur beim Speichern",
    },
}


def luecken(daten: dict[str, tuple[str, list]]) -> list[str]:
    """Felder, die in keiner Antwort belegt sind (immer ``null`` oder leere Liste)."""
    gesehen: dict[str, set[str]] = {}

    def lauf(wert, weg: str):
        if isinstance(wert, dict):
            gesehen.setdefault(weg, set()).add("wert")
            for name, inhalt in wert.items():
                lauf(inhalt, f"{weg}.{name}")
        elif isinstance(wert, list):
            gesehen.setdefault(weg, set()).add("voll" if wert else "leer")
            for eintrag in wert:
                lauf(eintrag, f"{weg}[]")
        else:
            gesehen.setdefault(weg, set()).add("null" if wert is None else "wert")

    for name, (_typ, antworten) in daten.items():
        for antwort in antworten:
            lauf(antwort, f"{name}[]")
    return sorted(weg for weg, arten in gesehen.items() if arten <= {"null", "leer"})


def formen(daten: dict[str, tuple[str, list]]) -> dict:
    return {name: [typ, form(antworten)] for name, (typ, antworten) in daten.items()}


def als_json(bereich: str, daten: dict[str, tuple[str, list]]) -> str:
    """Antworten je Abruf mit dem Typ der Oberfläche und der Datei, in der er steht."""
    quelle = BEREICHE[bereich][0]
    inhalt = {
        name: {"typ": typ, "quelle": quelle, "antworten": antworten}
        for name, (typ, antworten) in daten.items()
    }
    return json.dumps(inhalt, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def aus_json(text: str) -> dict[str, tuple[str, list]]:
    return {name: (e["typ"], e["antworten"]) for name, e in json.loads(text).items()}
