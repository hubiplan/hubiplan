"""Form der öffentlichen Schnittstelle der Vereinswebseite (``/api/public/site/v1/…``).

Die Vereinswebseite (eigenes Repository) liest nur diese Adressen und testet gegen eine
nachgebildete Schnittstelle. Damit die Nachbildung zum Server passt, hält der Server hier
fest, welche Felder jede Antwort hat: aus den Antworten für den Demoverein wird die „Form“
gebildet (Feldnamen und Arten der Werte, keine Inhalte) und in
``config/webseite_schnittstelle.json`` eingecheckt. Die Webseite prüft ihre Nachbildung
gegen eine Kopie dieser Datei.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from django.core.management import call_command
from django.test import Client

from organizations import demo_korps
from organizations.models import Organization
from website.models import BLOCKS, Website

DATEI = Path(__file__).resolve().parent.parent / "config" / "webseite_schnittstelle.json"
PREFIX = "/api/public/site/v1/"


def form(wert):
    """Feldnamen und Arten eines Werts, ohne Inhalte."""
    if isinstance(wert, dict):
        return {k: form(v) for k, v in sorted(wert.items())}
    if isinstance(wert, list):
        zusammen = None
        for eintrag in wert:
            zusammen = vereinen(zusammen, form(eintrag)) if zusammen is not None else form(eintrag)
        return [zusammen] if zusammen is not None else []
    if wert is None:
        return "null"
    if isinstance(wert, bool):
        return "bool"
    if isinstance(wert, (int, float)):
        return "zahl"
    return "text"


def _arten(a) -> set[str]:
    return set(a.split("|")) if isinstance(a, str) else set()


def vereinen(a, b):
    """Zwei Formen zusammenlegen: Felder beider Seiten, Arten als Auswahl („text|null“)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for k in sorted({*a, *b}):
            if k in a and k in b:
                out[k] = vereinen(a[k], b[k])
            else:
                # Feld fehlt in manchen Einträgen
                out[k] = vereinen(a.get(k, b.get(k)), "fehlt")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if not a or not b:
            return a or b
        return [vereinen(a[0], b[0])]
    if isinstance(a, str) and isinstance(b, str):
        return "|".join(sorted(_arten(a) | _arten(b)))
    # Verschiedene Bauarten (z. B. Liste oder null): beide festhalten
    einfach, bau = (a, b) if isinstance(a, str) else (b, a)
    if isinstance(einfach, str) and not isinstance(bau, str):
        if isinstance(bau, dict) and "?" in bau:
            return {**bau, "?": vereinen(bau["?"], einfach)}
        return {"?": einfach, "form": bau} if isinstance(bau, list) else {**bau, "?": einfach}
    return {"auswahl": [a, b]}


def demoverein() -> Website:
    call_command("seed_demoverein", password="Test-Passwort-123", stdout=io.StringIO())
    club = Organization.objects.get(name=demo_korps.CLUB_NAME)
    website = Website.objects.get(organization=club)
    # Öffentlich und mit allen Bausteinen: So antwortet möglichst jede Adresse
    website.state = "public"
    website.blocks = {**(website.blocks or {}), **{name: True for name in BLOCKS}}
    website.save(update_fields=["state", "blocks"])
    return website


def _json(client: Client, pfad: str):
    antwort = client.get(PREFIX + pfad, HTTP_ACCEPT="application/json")
    if antwort.status_code == 404:
        return None
    assert antwort.status_code == 200, f"{pfad}: {antwort.status_code}"
    return antwort.json()


def antworten(website: Website) -> dict[str, object]:
    """Adresse (mit Platzhaltern) → Antwort für den Demoverein."""
    client = Client()
    key = website.public_key
    out: dict[str, object] = {}

    def hole(name: str, pfad: str):
        antwort = _json(client, f"{key}/{pfad}")
        if antwort is not None:
            out[name] = antwort
        return antwort

    out["instance/"] = _json(client, "instance/")
    info = hole("", "")
    for pfad in (
        "board/",
        "bookings/",
        "contact/",
        "documents/",
        "events/",
        "galleries/",
        "honors/",
        "imprint/",
        "join/",
        "memorial/",
        "posts/",
        "repertoire/",
        "results/",
        "units/",
    ):
        hole(pfad, pfad)
    hole("search/", "search/?q=Musterstadt")
    einheiten = (out.get("units/") or {}).get("units") or []
    if einheiten:
        hole("units/<slug>/", f"units/{einheiten[0]['slug']}/")
    ergebnisse = out.get("results/") or {}
    for wettbewerb in ergebnisse.get("competitions") or []:
        hole("results/<token>/", f"results/{wettbewerb['id']}/")
        hole("results/<token>/version/", f"results/{wettbewerb['id']}/version/")
        break
    for reihe in ergebnisse.get("series") or []:
        hole("results/series/<token>/", f"results/series/{reihe['id']}/")
        break
    alben = (out.get("galleries/") or {}).get("galleries") or []
    if alben:
        hole("galleries/<slug>/", f"galleries/{alben[0]['slug']}/")
    for seite in info.get("pages") or []:
        if isinstance(seite, dict) and seite.get("slug"):
            hole("pages/<slug>/", f"pages/{seite['slug']}/")
            break
    return out


# Adressen mit JSON-Antwort, die der Demoverein (noch) nicht belegt; hier nur genannt, damit
# die Lücke sichtbar ist. Dateien, Bilder und Kalender (.ics) haben keine Felder.
ALLE = (
    "",
    "board/",
    "bookings/",
    "contact/",
    "documents/",
    "events/",
    "galleries/",
    "galleries/<slug>/",
    "honors/",
    "imprint/",
    "instance/",
    "join/",
    "memorial/",
    "pages/<slug>/",
    "posts/",
    "repertoire/",
    "results/",
    "results/<token>/",
    "results/<token>/version/",
    "results/series/<token>/",
    "search/",
    "units/",
    "units/<slug>/",
)


def formen(website: Website) -> dict[str, object]:
    belegt = {name: form(wert) for name, wert in sorted(antworten(website).items())}
    return {
        "antworten": belegt,
        "ohne_beispiel": sorted(set(ALLE) - set(belegt)),
    }


def text(daten: dict[str, object]) -> str:
    return json.dumps(daten, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
