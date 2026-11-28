"""Form der öffentlichen Schnittstelle der Vereinswebseite (``/api/public/site/v1/…``).

Die Vereinswebseite (eigenes Repository) liest nur diese Adressen. Damit sie zum Server
passt, hält der Server zwei Dateien fest:

- ``config/webseite_schnittstelle.json``: die „Form“ jeder Antwort (Feldnamen und Arten der
  Werte, keine Inhalte).
- ``config/webseite_antworten.json``: die echten Antworten aller Adressen für die
  Beispielvereine. Die Webseite baut daraus in ihren Tests jede Seite.

Beispielvereine sind der Prüfverein (Demoverein, in dem ``webseite_pruefverein`` jedes Feld
belegt) und die Demokapelle. ``luecken`` nennt Felder, die kein Beispiel belegt; die Liste
muss leer bleiben.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

from django.core.management import call_command
from django.test import Client

from organizations import demo_kapelle, demo_korps
from organizations.models import Organization
from website.models import BLOCKS, Website

CONFIG = Path(__file__).resolve().parent.parent / "config"
DATEI = CONFIG / "webseite_schnittstelle.json"
ANTWORTEN = CONFIG / "webseite_antworten.json"
PREFIX = "/api/public/site/v1/"


# Schlüssel mit laufender Nummer (z. B. „membertype:17“ unter ``names``) zählen als einer
NUMMER = re.compile(r"^(\w+):\d+$")


def form(wert):
    """Feldnamen und Arten eines Werts, ohne Inhalte."""
    if isinstance(wert, dict):
        out: dict = {}
        for k, v in sorted(wert.items()):
            k = NUMMER.sub(r"\1:<nr>", k)
            out[k] = vereinen(out[k], form(v)) if k in out else form(v)
        return out
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


def _zerlegt(f) -> tuple[set[str], list | None, dict | None]:
    """Form in ihre Bauarten: einfache Arten, Liste, Felder eines Objekts."""
    if isinstance(f, str):
        return _arten(f), None, None
    if isinstance(f, list):
        return set(), f, None
    felder = {k: v for k, v in f.items() if k not in ("?", "?liste")}
    return _arten(f.get("?", "")) - {""}, f.get("?liste"), felder or (None if "?liste" in f else {})


def vereinen(a, b):
    """Zwei Formen zusammenlegen: Felder beider Seiten, Arten als Auswahl („text|null“).

    Kommt ein Wert in mehreren Bauarten vor (Objekt oder ``null``, Liste oder fehlend),
    stehen die einfachen Arten unter „?“ und die Liste unter „?liste“ neben den Feldern."""
    arten_a, liste_a, felder_a = _zerlegt(a)
    arten_b, liste_b, felder_b = _zerlegt(b)
    arten = arten_a | arten_b
    if liste_a is None or liste_b is None:
        liste = liste_a if liste_b is None else liste_b
    elif not liste_a or not liste_b:
        liste = liste_a or liste_b
    else:
        liste = [vereinen(liste_a[0], liste_b[0])]
    if felder_a is None or felder_b is None:
        felder = felder_a if felder_b is None else felder_b
    else:
        felder = {}
        for k in sorted({*felder_a, *felder_b}):
            if k in felder_a and k in felder_b:
                felder[k] = vereinen(felder_a[k], felder_b[k])
            else:
                # Feld fehlt in manchen Einträgen
                felder[k] = vereinen(felder_a.get(k, felder_b.get(k)), "fehlt")
    if liste is None and felder is None:
        return "|".join(sorted(arten))
    if not arten and felder is None:
        return liste
    out = dict(felder or {})
    if arten:
        out["?"] = "|".join(sorted(arten))
    if liste is not None:
        out["?liste"] = liste
    return out


def _oeffentlich(befehl: str, name: str, schluessel: str) -> Website:
    call_command(befehl, password="Test-Passwort-123", stdout=io.StringIO())
    club = Organization.objects.get(name=name)
    website = Website.objects.get(organization=club)
    # Öffentlich und mit allen Bausteinen: So antwortet möglichst jede Adresse
    website.state = "public"
    website.blocks = {**(website.blocks or {}), **{name: True for name in BLOCKS}}
    # fester Schlüssel: Die aufgezeichneten Antworten ändern sich so nicht mit jedem Lauf
    website.public_key = schluessel
    website.save(update_fields=["state", "blocks", "public_key"])
    return website


def demoverein() -> Website:
    return _oeffentlich("seed_demoverein", demo_korps.CLUB_NAME, "demoverein-musterstadt")


def demokapelle() -> Website:
    return _oeffentlich("seed_demokapelle", demo_kapelle.CLUB_NAME, "demokapelle-musterdorf")


def _json(client: Client, pfad: str):
    antwort = client.get(PREFIX + pfad, HTTP_ACCEPT="application/json")
    if antwort.status_code == 404:
        return None
    assert antwort.status_code == 200, f"{pfad}: {antwort.status_code}"
    return antwort.json()


def _vorschau(website: Website) -> str:
    """Gültige Vorschau-Sitzung (wie nach dem Öffnen der Vorschau in HUBIplan)."""
    from django.core import signing
    from django.utils import timezone

    from website import services

    bis = timezone.now().timestamp() + 600
    return signing.dumps({"w": website.public_key, "u": bis}, salt=services._SALT_SESSION)


def abrufe(website: Website, vorschau: bool = False) -> list[tuple[str, str, object]]:
    """Alle Abrufe für eine Webseite: (Adresse mit Platzhaltern, Pfad hinter dem Präfix,
    Antwort). Listen werden ganz durchlaufen (jede Untereinheit, jedes Album …), damit die
    Form alle Ausprägungen sieht."""
    kopf = {"HTTP_X_PREVIEW_SESSION": _vorschau(website)} if vorschau else {}
    client = Client(**kopf)
    key = website.public_key
    out: list[tuple[str, str, object]] = []

    def hole(name: str, pfad: str, mit_key: bool = True):
        ganz = f"{key}/{pfad}" if mit_key else pfad
        antwort = _json(client, ganz)
        if antwort is not None:
            out.append((name, ganz, antwort))
        return antwort or {}

    hole("instance/", "instance/", mit_key=False)
    domain = website.domains.first()
    if domain is not None:
        hole("resolve/", f"resolve/?host={domain.hostname}", mit_key=False)
    info = hole("", "")
    for pfad in (
        "board/",
        "bookings/",
        "contact/",
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
    for bereich in ("press", "documents"):
        hole("documents/", f"documents/?section={bereich}")
    hole("search/", "search/?q=Muster")
    for paket in info.get("design_packages") or {}:
        hole("design/<key>/", f"design/{paket}/")
    for einheit in info.get("units") or []:
        hole("units/<slug>/", f"units/{einheit['slug']}/")
        hole("events/", f"events/?einheit={einheit['slug']}")
        hole("posts/", f"posts/?einheit={einheit['slug']}")
    for punkt in info.get("nav") or []:
        for eintrag in [punkt, *(punkt.get("children") or [])]:
            if eintrag.get("key") == "membertype" and eintrag.get("id"):
                hole("members/<slug>/", f"members/{eintrag['id']}/")
    ergebnisse = next((a for n, _p, a in out if n == "results/"), {})
    # Die Webseite fragt mit dem Kurznamen aus der Übersicht (lesbare Adressen) und für den
    # Stand laufender Wettbewerbe mit der Kennung; beides liefert dasselbe
    for wettbewerb in ergebnisse.get("competitions") or []:
        for kennung in sorted({wettbewerb["id"], wettbewerb.get("slug") or wettbewerb["id"]}):
            hole("results/<token>/", f"results/{kennung}/")
            hole("results/<token>/version/", f"results/{kennung}/version/")
    for reihe in ergebnisse.get("series") or []:
        for kennung in sorted({reihe["id"], reihe.get("slug") or reihe["id"]}):
            hole("results/series/<token>/", f"results/series/{kennung}/")
    # Startseite: die neuesten Wettbewerbe mit Siegern (Wertungen, Preise, Stand)
    hole("results/", "results/?start=1")
    alben = next((a for n, _p, a in out if n == "galleries/"), {})
    offen = [a["slug"] for a in alben.get("albums") or []]
    while offen:
        album = hole("galleries/<slug>/", f"galleries/{offen.pop()}/")
        offen += [a["slug"] for a in album.get("albums") or []]
    termine = next((a for n, _p, a in out if n == "events/"), {})
    seiten = {"geschichte"}  # die Chronik steht nicht immer im Menü
    seiten |= {s["slug"] for s in info.get("menu") or []}
    seiten |= {e["page"] for e in termine.get("events") or [] if e.get("page")}
    for slug in sorted(seiten):
        hole("pages/<slug>/", f"pages/{slug}/")
    slugs = {
        b["slug"]
        for n, _p, a in out
        if n == "posts/"
        for b in a.get("posts") or []
        if b.get("slug")
    }
    for slug in sorted(slugs):
        hole("posts/eigene/<slug>/", f"posts/eigene/{slug}/")
    return out


# Adressen mit JSON-Antwort. Dateien, Bilder, Kalender (.ics) und die Vorschau-Anmeldung
# (POST) haben keine Felder und stehen in OHNE_FELDER.
ALLE = (
    "",
    "board/",
    "bookings/",
    "contact/",
    "design/<key>/",
    "documents/",
    "events/",
    "galleries/",
    "galleries/<slug>/",
    "honors/",
    "imprint/",
    "instance/",
    "join/",
    "members/<slug>/",
    "memorial/",
    "pages/<slug>/",
    "posts/",
    "posts/eigene/<slug>/",
    "repertoire/",
    "resolve/",
    "results/",
    "results/<token>/",
    "results/<token>/version/",
    "results/series/<token>/",
    "search/",
    "units/",
    "units/<slug>/",
)


# Adressen ohne Felder: Dateien, Bilder, Kalender und die Anmeldung der Vorschau (POST)
OHNE_FELDER = (
    "bookings.ics",
    "events.ics",
    "events/attachments/<pk>/",
    "fee-rules/preview/",
    "files/<token>/",
    "founding-deed/preview/",
    "honors/photos/<token>/",
    "icon-<name>.png",
    "images/<image_key>/",
    "photos/<token>/",
    "posts/images/<image_key>/",
    "preview/",
    "statute/preview/",
)


def leerer_verein() -> Website:
    """Ein Verein ohne Inhalte, alle Bereiche eingeschaltet: zeigt, was leer bleiben darf."""
    from .factories import make_org, make_website

    module = Organization.objects.get(name=demo_korps.CLUB_NAME).enabled_modules
    club = make_org("Leerer Musterverein", enabled_modules=list(module))
    return make_website(
        club,
        public_key="leerer-musterverein",
        state="public",
        blocks={name: True for name in BLOCKS},
    )


def alle_abrufe() -> list[tuple[str, str, str, object]]:
    """Abrufe aller Beispiele als (Beispiel, Adresse, Pfad, Antwort): der Demoverein, wie er
    ist; derselbe als Prüfverein, in dem jedes Feld belegt ist; die Demokapelle; ein leerer
    Verein. So zeigt die Form sowohl die belegten Felder als auch, was leer oder ``null``
    sein darf."""
    from . import webseite_pruefverein

    verein = demoverein()
    out = [("demoverein", *abruf) for abruf in abrufe(verein)]
    voll = webseite_pruefverein.fuelle(verein)
    out += [("pruefverein", *abruf) for abruf in abrufe(voll)]
    # In der Vorschau kommen die Adressen für den Rahmen und Platzhalter für fehlende Bilder
    out += [("pruefverein-vorschau", *abruf) for abruf in abrufe(voll, vorschau=True)]
    out += [("demokapelle", *abruf) for abruf in abrufe(demokapelle())]
    out += [("leer", *abruf) for abruf in abrufe(leerer_verein())]
    return out


# Gleiche Bauteile an mehreren Stellen: Abschnitte gibt es auf der Startseite, auf den Seiten
# der Untereinheiten und auf Textseiten, überall mit denselben Arten.
ABSCHNITTE = (
    ("", "home_layout"),
    ("units/<slug>/", "sections"),
    ("pages/<slug>/", "sections"),
    ("memorial/", "intro", "sections"),
)
# Zuordnungen mit freien Schlüsseln (Name des Designs, Bereich, Baustein): alle Werte haben
# dieselbe Form, in der Datei steht sie unter „*“.
ZUORDNUNGEN = (
    ("", "designs"),
    ("", "design_catalog"),
    ("", "design_packages"),
    ("", "intros"),
    ("", "names"),
    ("design/<key>/", "templates"),
)


def _an(belegt: dict, weg: tuple):
    """Elternteil und Schlüssel der Stelle ``weg`` oder None, wenn es sie nicht gibt."""
    teil = belegt.get(weg[0])
    for name in weg[1:-1]:
        teil = teil.get(name) if isinstance(teil, dict) else None
    return (teil, weg[-1]) if isinstance(teil, dict) and weg[-1] in teil else None


def _angleichen(belegt: dict) -> None:
    stellen = [s for s in (_an(belegt, weg) for weg in ABSCHNITTE) if s]
    gemeinsam = None
    for teil, name in stellen:
        gemeinsam = teil[name] if gemeinsam is None else vereinen(gemeinsam, teil[name])
    for teil, name in stellen:
        teil[name] = gemeinsam
    # Ziele (Menüpunkt, Untereinheit, Termin, Link) haben überall dieselbe Form
    ziele = [s for s in (_an(belegt, ("", "notice", "target")),) if s]
    if stellen and isinstance(gemeinsam, list) and gemeinsam:
        for liste in ("buttons", "tiles"):
            eintraege = gemeinsam[0].get(liste)
            if isinstance(eintraege, dict):
                eintraege = eintraege.get("?liste")
            if isinstance(eintraege, list) and eintraege and "target" in eintraege[0]:
                ziele.append((eintraege[0], "target"))
    ziel = None
    for teil, name in ziele:
        ziel = teil[name] if ziel is None else vereinen(ziel, teil[name])
    for teil, name in ziele:
        teil[name] = ziel
    for weg in ZUORDNUNGEN:
        stelle = _an(belegt, weg)
        if not stelle or not isinstance(stelle[0][stelle[1]], dict):
            continue
        teil, name = stelle
        werte = [v for k, v in teil[name].items() if k not in ("?", "?liste")]
        eine = None
        for wert in werte:
            # „fehlt“ entsteht nur, weil nicht jedes Beispiel jeden Schlüssel hat
            if isinstance(wert, str):
                wert = "|".join(sorted(_arten(wert) - {"fehlt"})) or "fehlt"
            elif isinstance(wert, dict) and "?" in wert:
                rest = "|".join(sorted(_arten(wert["?"]) - {"fehlt"}))
                wert = {k: v for k, v in wert.items() if k != "?"} | ({"?": rest} if rest else {})
            eine = wert if eine is None else vereinen(eine, wert)
        teil[name] = {"*": eine} if eine is not None else {}


def formen(abrufe_: list[tuple[str, str, str, object]]) -> dict[str, object]:
    """Form aller Antworten; mehrere Vereine und Ausprägungen werden zusammengelegt."""
    belegt: dict[str, object] = {}
    for _beispiel, name, _pfad, wert in abrufe_:
        neu = form(wert)
        belegt[name] = vereinen(belegt[name], neu) if name in belegt else neu
    _angleichen(belegt)
    ueberholt = _ergaenzen(belegt)
    assert not ueberholt, f"OHNE_BEISPIEL: inzwischen belegt: {ueberholt}"
    return {
        "antworten": dict(sorted(belegt.items())),
        "ohne_beispiel": sorted(set(ALLE) - set(belegt)),
    }


# Felder, die an dieser Stelle nie belegt sind; mit Grund, damit die Ausnahme prüfbar bleibt.
IMMER_LEER = {
    # Die Einleitung der Gedenkseite ist eine Textseite: Zeitleiste hat nur die Chronik,
    # Termindaten nur eine Veranstaltungsseite (beides unter pages/<slug>/ belegt)
    "memorial/.intro.timeline",
    "memorial/.intro.event",
    # Eigene Beiträge haben keinen Link nach außen (posts/ belegt ihn für die Kanäle)
    "posts/eigene/<slug>/.post.permalink",
    # Abschnitte mit Terminen und Beiträgen liefern dieselben Einträge wie events/ und
    # posts/ (dort belegt); „owner“ hat nur ein Termin einer Einheit darüber, „unit“ nur
    # ein Beitrag einer Untereinheit auf der Hauptseite
    "/.home_layout[].event.owner",
    "/.home_layout[].events[].owner",
    "/.home_layout[].posts[].unit",
    # Pakete mit eigenen Vorlagen liefert der Server nicht mehr aus (Website.packages)
    "design/<key>/.templates",
}


# Felder, die der Server liefern kann, die aber kein Beispiel zeigt. Sie stehen von Hand in
# der Form; der Test prüft, dass sie wirklich fehlen (sonst hier streichen).
OHNE_BEISPIEL = {
    # Verein eines Gastes in der Rangliste (website/results.py, _row): braucht einen fremden
    # Wettbewerb mit gewerteten Gästen
    ("results/<token>/", "scorings", 0, "rows", 0, "club"): "fehlt|text",
    # dasselbe in den Siegern für die Startseite (results/?start=1)
    ("results/", "competitions", 0, "scorings", "?liste", 0, "rows", 0, "club"): "fehlt|text",
}


def _ergaenzen(belegt: dict) -> list[str]:
    """Trägt OHNE_BEISPIEL ein; nennt Einträge, die inzwischen ein Beispiel haben."""
    ueberholt = []
    for weg, art in OHNE_BEISPIEL.items():
        teil = belegt.get(weg[0])
        for name in weg[1:-1]:
            teil = teil[name]
        if weg[-1] in teil:
            ueberholt.append("/".join(map(str, weg)))
        teil[weg[-1]] = art
    return ueberholt


def luecken(daten: dict[str, object]) -> list[str]:
    """Felder, die kein Beispiel belegt: immer leer, immer ``null`` oder Adresse ohne Antwort."""
    out = [f"{name}: keine Antwort" for name in daten["ohne_beispiel"]]
    gefunden = _luecken(daten, out)
    # Abschnitte haben überall dieselbe Form (ABSCHNITTE): einmal nennen genügt
    doppelt = ("units/<slug>/.sections[]", "pages/<slug>/.sections[]", "memorial/.intro.sections[]")
    return [
        zeile
        for zeile in gefunden
        if zeile.split(":")[0] not in IMMER_LEER and not zeile.startswith(doppelt)
    ]


def _luecken(daten: dict[str, object], out: list[str]) -> list[str]:

    def lauf(f, weg: str):
        if isinstance(f, str):
            if _arten(f) <= {"null", "fehlt"}:
                out.append(f"{weg}: nur {f}")
        elif isinstance(f, list):
            if f:
                lauf(f[0], weg + "[]")
            else:
                out.append(f"{weg}: leere Liste")
        elif isinstance(f, dict):
            if not f:
                out.append(f"{weg}: leeres Objekt")
            for k, v in f.items():
                # „?“ hält nur fest, dass der Wert auch fehlen oder null sein darf
                if k == "?liste":
                    lauf(v, weg)
                elif k == "*":
                    lauf(v, f"{weg}.*")
                elif k != "?":
                    lauf(v, f"{weg}.{k}")

    for name, f in daten["antworten"].items():
        lauf(f, name or "/")
    return out


def arten_der_abschnitte(abrufe_: list[tuple[str, str, str, object]]) -> set[str]:
    """Arten der Abschnitte, die irgendeine Antwort wirklich liefert (Startseite, Seiten der
    Untereinheiten, Textseiten)."""
    arten: set[str] = set()
    for _beispiel, name, _pfad, antwort in abrufe_:
        if name == "":
            arten |= {a["kind"] for a in antwort.get("home_layout") or []}
        elif name in ("units/<slug>/", "pages/<slug>/"):
            arten |= {a["kind"] for a in antwort.get("sections") or []}
    return arten


def aufzeichnung(abrufe_: list[tuple[str, str, str, object]]) -> dict:
    """Die echten Antworten je Beispiel: Adresse, Pfad hinter ``/api/public/site/v1/`` und
    Antwort. Demoverein und Prüfverein haben denselben Schlüssel (es ist dieselbe Webseite,
    einmal wie angelegt und einmal mit allem belegt). ``stand`` ist der Zeitpunkt der
    Aufzeichnung: Termine und Fristen der Beispiele liegen von dort aus in der Zukunft, die
    Webseite stellt ihre Uhr in den Tests darauf."""
    from django.utils import timezone

    return {
        "stand": timezone.now().isoformat(timespec="seconds"),
        "antworten": [
            {"beispiel": beispiel, "adresse": name, "pfad": pfad, "antwort": antwort}
            for beispiel, name, pfad, antwort in abrufe_
        ],
    }


def text(daten: dict[str, object]) -> str:
    return json.dumps(daten, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
