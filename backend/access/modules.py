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
        "cards",
        gettext_noop("Mitgliedsausweise"),
        "members",
        gettext_noop("Ausweise mit QR-Code, Prüfseite und Wallet"),
        requires=("members",),
        org_types=("federation", "club"),
    ),
    Module(
        "portal",
        gettext_noop("Mitgliederbereich"),
        "members",
        gettext_noop("Mitglieder melden sich an und sehen ihre Daten, Termine und Rechnungen"),
        default=True,
        requires=("members",),
        org_types=("club",),
    ),
    Module(
        "awards",
        gettext_noop("Ehrungen & Jubiläen"),
        "members",
        gettext_noop("Ehrungen am Mitglied, Jubiläen und Mitgliedsdauer"),
        default=True,
        requires=("members",),
        org_types=("federation", "club"),
    ),
    Module(
        "honors",
        gettext_noop("Würden"),
        "members",
        gettext_noop("Würden wie König oder Prinz, Regentschaften und Königsliste"),
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
        "chronicle",
        gettext_noop("Chronik"),
        "life",
        gettext_noop("Zeitleiste der Vereinsgeschichte mit Kapiteln, Bildern und Excel-Import"),
        org_types=("federation", "club"),
    ),
    Module(
        "todos",
        gettext_noop("Aufgaben"),
        "life",
        gettext_noop("Eigene und geteilte Aufgaben mit Frist und Erinnerung"),
        default=True,
    ),
    Module(
        "music",
        gettext_noop("Musik"),
        "music",
        gettext_noop("Auftritte, Musiker, Proben, Notenausgabe und Besetzung"),
        requires=("events", "scores"),
        org_types=("federation", "club"),
    ),
    Module(
        "scores",
        gettext_noop("Notenarchiv"),
        "music",
        gettext_noop("Notenbestand mit Stücken, Arrangements, Stimmen und Notendateien"),
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
        "shooting",
        gettext_noop("Schießsport"),
        "competitions",
        gettext_noop("Schießscheiben mit Trefferbild und Fotoauswertung, Vogelschießen"),
        requires=("competitions",),
        org_types=("federation", "club"),
    ),
    Module(
        "entries",
        gettext_noop("Meldungen"),
        "competitions",
        gettext_noop("Meldungen an Veranstalter zusammenstellen und abgeben"),
        org_types=("federation", "club"),
    ),
    Module(
        "calls",
        gettext_noop("Ausschreibungen"),
        "competitions",
        gettext_noop("Ausschreibungen an Untereinheiten, Meldungen bestätigen"),
        org_types=("federation", "club"),
    ),
    Module(
        "circulars",
        gettext_noop("Rundschreiben"),
        "communication",
        gettext_noop("E-Mails, Serienbriefe und Briefe an Mitglieder"),
        default=True,
        org_types=("federation", "club"),
    ),
    Module(
        "docs",
        gettext_noop("Dokumente"),
        "communication",
        gettext_noop("Dokumentenablage mit Ordnern, Freigaben und Papierkorb"),
        default=True,
        org_types=("federation", "club"),
    ),
    Module(
        "social",
        gettext_noop("Social Media"),
        "communication",
        gettext_noop("Beiträge aus Instagram und Facebook übernehmen und auf der Webseite zeigen"),
        requires=("website",),
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
        "tax",
        gettext_noop("Steuern & Gemeinnützigkeit"),
        "admin",
        gettext_noop("Steuerliche Bereiche in der Kasse, Auswertung nach Bereichen und Rücklagen"),
        requires=("finance",),
    ),
    Module(
        "donations",
        gettext_noop("Zuwendungsbestätigungen"),
        "admin",
        gettext_noop("Zuwendungen erfassen und Bestätigungen nach amtlichem Muster ausstellen"),
        requires=("finance",),
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
    Module(
        "bookings",
        gettext_noop("Belegung"),
        "admin",
        gettext_noop("Buchungskalender und Anfragen für Material, Räume und Anlagen"),
        requires_any=("material", "infrastructure"),
        org_types=("federation", "club"),
    ),
    Module(
        "mcp",
        gettext_noop("KI-Assistenten"),
        "admin",
        gettext_noop(
            "KI-Assistenten mit HUBIplan verbinden, die Webseite als Entwurf bearbeiten "
            "(nur mit dem Zusatzrecht und Zwei-Faktor-Anmeldung)"
        ),
        requires=("website",),
    ),
)

# Module, die eine Untereinheit selbst führt (eigener Arbeitsbereich); alle übrigen gelten
# für eine Untereinheit, wenn ihr Verein sie eingeschaltet hat.
UNIT_OWN_MODULES = frozenset({"finance", "billing", "website"})

MODULE_BY_ID: dict[str, Module] = {m.id: m for m in MODULES}
MODULE_IDS: tuple[str, ...] = tuple(m.id for m in MODULES)
DEFAULT_IDS: tuple[str, ...] = tuple(m.id for m in MODULES if m.default)


@dataclass(frozen=True)
class Extra:
    """Zusatzfunktion eines Moduls: ein Schalter der Einheit, keine eigenen Seiten.

    ``field`` ist das Feld an der Organisation bzw. (``store="billing"``) an den
    Beitragseinstellungen. Die Einrichtungsseiten der Module schalten dasselbe Feld."""

    id: str
    label: str
    module: str
    field: str
    store: str = "org"
    # Nur wenn der Betreiber die Anbindung eingerichtet hat (siehe extra_available)
    needs_service: str = ""


EXTRAS: tuple[Extra, ...] = (
    Extra(
        "photo_approval",
        gettext_noop("Hochgeladene Mitgliederfotos erst nach Freigabe anzeigen"),
        "members",
        "photo_approval_required",
    ),
    Extra(
        "contact_approval",
        gettext_noop("Geänderte Kontaktdaten erst nach Bestätigung übernehmen"),
        "portal",
        "contact_changes_need_approval",
    ),
    Extra(
        "wallet",
        gettext_noop("Ausweis in Apple Wallet und Google Wallet"),
        "cards",
        "card_wallet_enabled",
        needs_service="wallet",
    ),
    Extra(
        "cash_counts",
        gettext_noop("Zählprotokoll und Kassenbericht für Feste"),
        "finance",
        "cash_counts_enabled",
    ),
    Extra("datev", gettext_noop("DATEV-Export"), "finance", "datev_enabled"),
    Extra(
        "tax_areas",
        gettext_noop("Steuerliche Bereiche in der Kasse"),
        "tax",
        "tax_areas_enabled",
    ),
    Extra("reserves", gettext_noop("Rücklagen führen"), "tax", "reserves_enabled"),
    Extra("sepa", gettext_noop("SEPA-Lastschrift"), "billing", "sepa_enabled", store="billing"),
)
EXTRA_BY_ID: dict[str, Extra] = {e.id: e for e in EXTRAS}


def extra_available(extra: Extra) -> bool:
    """Gibt es die Zusatzfunktion auf dieser Instanz (Anbindung eingerichtet)?"""
    if extra.needs_service == "wallet":
        from cards import apple, wallet

        return wallet.enabled() or apple.enabled()
    return True


def _extra_target(org, extra: Extra):
    if extra.store == "billing":
        from billing.services import settings_for

        return settings_for(org)
    return org


def extra_on(org, extra: Extra) -> bool:
    if extra.store == "billing":
        from billing.models import BillingSettings

        return BillingSettings.objects.filter(organization=org, **{extra.field: True}).exists()
    return bool(getattr(org, extra.field))


def set_extra(org, extra: Extra, on: bool) -> bool:
    """Schalter setzen und speichern; True, wenn sich etwas geändert hat."""
    target = _extra_target(org, extra)
    if bool(getattr(target, extra.field)) == on:
        return False
    setattr(target, extra.field, on)
    target.save(update_fields=[extra.field])
    return True


@dataclass(frozen=True)
class Template:
    """Vorlage beim Anlegen einer Einheit (M6): schlägt Module und Bezeichnungen vor.

    Gespeichert wird nur das Ergebnis, nicht die Vorlage."""

    id: str
    label: str
    org_type: str
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    # Bezeichnung der Untereinheiten: Einzahl, Mehrzahl, Genus (leer: unverändert)
    units: tuple[str, str, str] | None = None


TEMPLATES: tuple[Template, ...] = (
    Template(
        "general",
        gettext_noop("Allgemeiner Verein"),
        "club",
        units=(gettext_noop("Abteilung"), gettext_noop("Abteilungen"), "f"),
    ),
    Template(
        "shooting",
        gettext_noop("Schützenverein"),
        "club",
        add=(
            "honors",
            "chronicle",
            "cards",
            "competitions",
            "shooting",
            "material",
            "infrastructure",
            "bookings",
            "tax",
        ),
        units=(gettext_noop("Zug"), gettext_noop("Züge"), "m"),
    ),
    Template(
        "music",
        gettext_noop("Musikverein / Kapelle"),
        "club",
        add=("music", "scores", "chronicle", "material", "tax"),
        units=(gettext_noop("Register"), gettext_noop("Register"), "n"),
    ),
    Template(
        "choir",
        gettext_noop("Chor"),
        "club",
        add=("scores", "chronicle"),
        units=(gettext_noop("Stimme"), gettext_noop("Stimmen"), "f"),
    ),
    Template(
        "sports",
        gettext_noop("Sportverein"),
        "club",
        add=("competitions", "helpers", "cards", "infrastructure", "bookings", "tax"),
        units=(gettext_noop("Abteilung"), gettext_noop("Abteilungen"), "f"),
    ),
    Template(
        "support",
        gettext_noop("Förderverein"),
        "club",
        add=("donations",),
        remove=("events", "awards"),
    ),
    Template(
        "federation",
        gettext_noop("Dachverband"),
        "federation",
        add=("calls", "circulars"),
    ),
)


def template_modules(template: Template) -> list[str]:
    """Module einer Vorlage: Vorgabe plus Zusätze, ohne Gestrichenes, mit Voraussetzungen."""
    wanted = (set(DEFAULT_IDS) | set(template.add)) - set(template.remove)
    ids = without_dependents(with_requirements(wanted))
    return sorted(m for m in ids if template.org_type in MODULE_BY_ID[m].org_types)


def _template_units(tpl: Template) -> dict | None:
    """Bezeichnung der Untereinheiten: deutsch wie gespeichert, dazu englisch."""
    if not tpl.units:
        return None
    from django.utils import translation

    label, plural, gender = tpl.units
    with translation.override("en"):
        label_en, plural_en = gettext(label), gettext(plural)
    return {
        "label": label,
        "plural": plural,
        "gender": gender,
        "label_en": label_en,
        "plural_en": plural_en,
    }


def templates() -> list[dict]:
    return [
        {
            "id": tpl.id,
            "label": gettext(tpl.label),
            "org_type": tpl.org_type,
            "modules": template_modules(tpl),
            "units": _template_units(tpl),
        }
        for tpl in TEMPLATES
    ]


# Stand des Verzeichnisses für Exportdateien: 1 = bis M1, 2 = mit Aufgaben, Dokumenten,
# Rundschreiben, Ausweisen, Ausschreibungen, Belegung, Ehrungen & Jubiläen, Würden,
# Mitgliederbereich und Social Media als eigene Module; 3 = mit Chronik; 4 = mit Steuern &
# Gemeinnützigkeit und Zuwendungsbestätigungen; 5 = mit Notenarchiv; 6 = mit Schießsport
MODULES_SCHEMA = 6


def upgrade_modules(
    ids,
    schema: int,
    *,
    org_type: str = "club",
    has_cards: bool = False,
    has_honors: bool = False,
    has_social: bool = False,
    has_chronicle: bool = False,
    has_tax: bool = False,
    has_donations: bool = False,
):
    """Module aus einem älteren Stand so ergänzen, dass nichts verschwindet."""
    modules = set(ids or [])
    if schema < 2 and org_type in ("federation", "club"):
        modules |= {"todos", "docs", "circulars"}
        if "members" in modules:
            modules.add("awards")
        if "entries" in modules:
            modules.add("calls")
        if modules & {"material", "infrastructure"}:
            modules.add("bookings")
        if has_cards and "members" in modules:
            modules.add("cards")
        if has_honors:
            modules.add("honors")
    if schema < 2 and has_social and "website" in modules:
        modules.add("social")
    if schema < 3 and has_chronicle and org_type in ("federation", "club"):
        modules.add("chronicle")
    if schema < 4 and has_tax and "finance" in modules:
        modules.add("tax")
    if schema < 4 and has_donations and "finance" in modules:
        modules.add("donations")
    if schema < 5 and "music" in modules:
        modules.add("scores")
    if schema < 6 and "competitions" in modules:
        modules.add("shooting")
    return modules


def module_on(org, module_id: str) -> bool:
    """Ist das Modul für diese Einheit eingeschaltet? Untereinheiten erben vom Verein."""
    if org is None:
        return False
    if getattr(org, "type", None) == "unit":
        owner = org.organization
        if owner is None or module_id not in (owner.enabled_modules or []):
            return False
        if module_id not in UNIT_OWN_MODULES:
            return module_id not in unit_hidden(org)
    return module_id in (org.enabled_modules or [])


def unit_hidden(unit) -> set[str]:
    """Module, die der Verein für diese Untereinheit oder eine darüber ausgeblendet hat."""
    hidden = set(unit.unit_hidden_modules or [])
    parent = unit
    while parent.parent_id and parent.parent_id != parent.organization_id:
        parent = parent.parent
        if parent is None or parent.type != "unit":
            break
        hidden |= set(parent.unit_hidden_modules or [])
    return hidden


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


# --- Freigabe (Plattform) und Einschalten (Einheit) ---


def released_of(org) -> set[str]:
    """Von der Plattform freigegebene Module; ältere Stände ohne Freigabe: die eingeschalteten."""
    released = getattr(org, "released_modules", None) or org.enabled_modules or []
    return {m for m in released if m in MODULE_BY_ID}


def apply_release(org, released) -> None:
    """Freigabe der Plattform setzen. Neu freigegebene Module werden eingeschaltet (wie bisher),
    nicht mehr freigegebene ausgeschaltet; Daten bleiben erhalten. Speichert nicht."""
    old = released_of(org)
    new = with_requirements(released)
    enabled = (set(org.enabled_modules or []) & new) | (new - old)
    org.released_modules = sorted(new)
    org.enabled_modules = sorted(without_dependents(enabled))


class ModuleChoiceError(ValueError):
    pass


def apply_enabled(org, wanted) -> tuple[set[str], set[str]]:
    """Einheit schaltet Module ein oder aus, nur innerhalb der Freigabe. Voraussetzungen werden
    mitgenommen, abhängige Module mit ausgeschaltet. Gibt (zusätzlich ein, zusätzlich aus)
    gegenüber dem Wunsch zurück. Speichert nicht."""
    wanted = set(wanted or [])
    unknown = wanted - set(MODULE_BY_ID)
    if unknown:
        raise ModuleChoiceError(
            gettext("Unbekannte Module: {x}").format(x=", ".join(sorted(unknown)))
        )
    released = released_of(org)
    blocked = wanted - released
    if blocked:
        raise ModuleChoiceError(
            gettext("Nicht freigegeben: {x}").format(
                x=", ".join(gettext(MODULE_BY_ID[m].label) for m in sorted(blocked))
            )
        )
    before = set(org.enabled_modules or [])
    switched_off = before - wanted
    # Voraussetzungen mitnehmen, außer sie wurden gerade ausgeschaltet
    result = wanted
    for _ in range(len(MODULES)):
        extra = with_requirements(result) - result - switched_off
        if not extra:
            break
        missing = extra - released
        if missing:
            raise ModuleChoiceError(
                gettext("Dafür muss die Plattform auch freigeben: {x}").format(
                    x=", ".join(gettext(MODULE_BY_ID[m].label) for m in sorted(missing))
                )
            )
        result |= extra
    result = without_dependents(result)
    org.released_modules = sorted(released)
    org.enabled_modules = sorted(result)
    return result - wanted, wanted - result
