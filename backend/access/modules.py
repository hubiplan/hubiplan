"""Modulverzeichnis: alle abschaltbaren Module an einer Stelle.

Konzept: konzepte/module-neustruktur.md. Ein Modul hat eigene Seiten, eigene Daten und oft
eigene Bereiche im Rechtekatalog (``access/catalog.py``, ``Area.module``). Die Plattform gibt
Module frei, die Einheit schaltet sie ein. ``Organization.enabled_modules`` enthält die
eingeschalteten Module; alle Abfragen im Code lesen nur diese Liste.

Wer ein Modul abfragt, nutzt dessen ``id`` aus diesem Verzeichnis. ``tests/test_modulnamen.py``
prüft, dass es jede im Code abgefragte Kennung hier gibt.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop

ALL_TYPES = ("federation", "club", "unit")


@dataclass(frozen=True)
class Group:
    id: str
    label: str


@dataclass(frozen=True)
class Module:
    id: str
    label: str
    group: str
    description: str
    # Für neue Einheiten eingeschaltet
    default: bool = False
    # Muss eingeschaltet sein (wird beim Einschalten mitgenommen)
    requires: tuple[str, ...] = ()
    # Eines davon muss eingeschaltet sein
    requires_any: tuple[str, ...] = ()
    # Für welche Einheiten (Organization.type) es das Modul gibt
    org_types: tuple[str, ...] = ALL_TYPES


GROUPS: tuple[Group, ...] = (
    Group("members", gettext_noop("Mitglieder")),
    Group("life", gettext_noop("Vereinsleben")),
    Group("music", gettext_noop("Musik")),
    Group("competitions", gettext_noop("Wettbewerbe")),
    Group("communication", gettext_noop("Kommunikation")),
    Group("admin", gettext_noop("Verwaltung")),
)

MODULES: tuple[Module, ...] = (
    Module(
        "members",
        gettext_noop("Mitglieder"),
        "members",
        gettext_noop("Mitgliederliste, Akten, Ämter, Änderungen und Wechsel, Import"),
        default=True,
        org_types=("federation", "club"),
    ),
    Module(
        "events",
        gettext_noop("Termine"),
        "life",
        gettext_noop("Kalender mit Zu- und Absagen, Kalender-Abo und fremden Kalendern"),
        default=True,
    ),
    Module(
        "meetings",
        gettext_noop("Versammlungen"),
        "life",
        gettext_noop("Tagesordnung, Einladung, Protokoll und Beschlussbuch"),
        requires=("events",),
    ),
    Module(
        "helpers",
        gettext_noop("Helferdienste"),
        "life",
        gettext_noop("Dienstpläne mit Schichten und Einteilung"),
        requires=("events",),
    ),
    Module(
        "music",
        gettext_noop("Musik"),
        "music",
        gettext_noop("Auftritte, Musiker, Proben, Notenbestand und Besetzung"),
        requires=("events",),
        org_types=("federation", "club"),
    ),
    Module(
        "competitions",
        gettext_noop("Wettbewerbe"),
        "competitions",
        gettext_noop("Wettbewerbe mit Wertungen, Ranglisten, Wanderpokalen und Urkunden"),
        org_types=("federation", "club"),
    ),
    Module(
        "entries",
        gettext_noop("Meldungen"),
        "competitions",
        gettext_noop("Meldungen an Veranstalter und Ausschreibungen an Untereinheiten"),
        org_types=("federation", "club"),
    ),
    Module(
        "website",
        gettext_noop("Webseite"),
        "communication",
        gettext_noop("Inhalte und Einrichtung der Vereinswebseite"),
    ),
    Module(
        "finance",
        gettext_noop("Kasse"),
        "admin",
        gettext_noop("Kassenbuch, Konten, Belege, Abschluss"),
        default=True,
    ),
    Module(
        "billing",
        gettext_noop("Beiträge und Rechnungen"),
        "admin",
        gettext_noop("Beitragsläufe, Rechnungen, Mahnungen, Lastschrift"),
        default=True,
    ),
    Module(
        "material",
        gettext_noop("Material"),
        "admin",
        gettext_noop("Materialbestand, Standorte und Ausleihe"),
        org_types=("federation", "club"),
    ),
    Module(
        "infrastructure",
        gettext_noop("Räume und Anlagen"),
        "admin",
        gettext_noop("Vereinsheim, Schießstand, Plätze und ihre Bereiche"),
        org_types=("federation", "club"),
    ),
)

MODULE_BY_ID: dict[str, Module] = {m.id: m for m in MODULES}
MODULE_IDS: tuple[str, ...] = tuple(m.id for m in MODULES)
DEFAULT_IDS: tuple[str, ...] = tuple(m.id for m in MODULES if m.default)


def with_requirements(ids) -> set[str]:
    """Eingeschaltete Module samt allem, was sie voraussetzen."""
    result = {i for i in ids or [] if i in MODULE_BY_ID}
    changed = True
    while changed:
        changed = False
        for mid in list(result):
            module = MODULE_BY_ID[mid]
            for need in module.requires:
                if need not in result:
                    result.add(need)
                    changed = True
            if module.requires_any and not set(module.requires_any) & result:
                result.add(module.requires_any[0])
                changed = True
    return result


def without_dependents(ids) -> set[str]:
    """Module, deren Voraussetzung fehlt, fallen mit weg."""
    result = {i for i in ids or [] if i in MODULE_BY_ID}
    changed = True
    while changed:
        changed = False
        for mid in list(result):
            module = MODULE_BY_ID[mid]
            if not set(module.requires) <= result or (
                module.requires_any and not set(module.requires_any) & result
            ):
                result.discard(mid)
                changed = True
    return result


def directory() -> list[dict]:
    """Verzeichnis für Oberfläche und App, in der Sprache der Anfrage."""
    groups = []
    for group in GROUPS:
        modules = [
            {
                "id": m.id,
                "label": gettext(m.label),
                "description": gettext(m.description),
                "default": m.default,
                "requires": list(m.requires),
                "requires_any": list(m.requires_any),
                "org_types": list(m.org_types),
            }
            for m in MODULES
            if m.group == group.id
        ]
        if modules:
            groups.append({"id": group.id, "label": gettext(group.label), "modules": modules})
    return groups
