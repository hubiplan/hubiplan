"""Berechtigungskatalog: Bereiche mit drei Stufen (Ralf 02.11.2026).

Jede Rolle hat je Bereich *kein Zugriff*, *lesen* (``<bereich>.view``) oder *bearbeiten*
(``<bereich>.edit``, schließt Lesen ein). Dazu kommen wenige Zusatzrechte zum Ankreuzen
(Exporte, Ansicht als Rolle). Rollen von Einheiten und Rollen von Untereinheiten (Zug-Rollen
über die Mitgliedschaft) nutzen dieselben Bereiche; Untereinheiten bieten nur eine Auswahl.
Konzept: konzepte/berechtigungen.md.

Übergang (eine Fassung lang): Die Rollen speichern nur noch die neuen Codes. Für die
bisherigen Prüfstellen rechnet ``effective`` daraus die früheren Codes mit aus
(z. B. ``events.edit`` → ``events.manage``); alte Codes in Eingaben übersetzt ``normalize``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop

VIEW = "view"
EDIT = "edit"

# --- Frühere Codes (Prüfstellen, die noch nicht auf Bereiche umgestellt sind) ---
MEMBERS_VIEW = "members.view"
MEMBERS_EDIT = "members.edit"
PHOTOS_MANAGE = "photos.manage"
CARDS_MANAGE = "cards.manage"
ORG_EDIT = "org.edit"
AUDIT_VIEW = "audit.view"
ROLES_MANAGE = "roles.manage"
# HUBIplan so ansehen, wie eine Rolle der Einheit es sieht (nur lesen, nie mehr als die
# eigenen Rechte; siehe access/preview.py)
ROLES_PREVIEW = "roles.preview"
THEME_EDIT = "theme.edit"
EXPORT_RUN = "export.run"
PLATFORM_MANAGE = "platform.manage"
FINANCE_VIEW = "finance.view"
FINANCE_EDIT = "finance.edit"
DATA_EXPORT = "data.export"
CLUBS_MANAGE = "clubs.manage"
BILLING_VIEW = "billing.view"
BILLING_EDIT = "billing.edit"
EVENTS_MANAGE = "events.manage"
DOCS_VIEW = "docs.view"
DOCS_MANAGE = "docs.manage"
CIRCULARS_SEND = "circulars.send"
WEBSITE_MANAGE = "website.manage"
WEBSITE_CONTENT = "website.content"
PEERING_MANAGE = "peering.manage"
COMPETITIONS_MANAGE = "competitions.manage"
COMPETITIONS_RESULTS = "competitions.results"
ENTRIES_SUBMIT = "entries.submit"
ENTRIES_MANAGE = "entries.manage"

DEPT_MEMBERS_VIEW = "dept.members.view"
DEPT_MEMBERS_EDIT = "dept.members.edit"
DEPT_ROLES_MANAGE = "dept.roles.manage"
DEPT_ACCESS_MANAGE = "dept.access.manage"
DEPT_EXPORT = "dept.export"
DEPT_INVOICES_VIEW = "dept.invoices.view"
DEPT_CARDS_MANAGE = "dept.cards.manage"
DEPT_EVENTS_MANAGE = "dept.events.manage"
DEPT_DOCS_MANAGE = "dept.docs.manage"
DEPT_CIRCULARS_SEND = "dept.circulars.send"
DEPT_ENTRIES_SUBMIT = "dept.entries.submit"

# --- Neue Codes, die Prüfstellen direkt nutzen ---
PHOTOS_VIEW = "photos.view"
PHOTOS_EDIT = "photos.edit"
CARDS_VIEW = "cards.view"
CARDS_EDIT = "cards.edit"
SETTINGS_VIEW = "settings.view"
SETTINGS_EDIT = "settings.edit"
THEME_VIEW = "theme.view"
ROLES_VIEW = "roles.view"
ROLES_EDIT = "roles.edit"
EVENTS_VIEW = "events.view"
EVENTS_EDIT = "events.edit"
DOCS_EDIT = "docs.edit"
CIRCULARS_VIEW = "circulars.view"
CIRCULARS_EDIT = "circulars.edit"
WEBCONTENT_VIEW = "webcontent.view"
WEBCONTENT_EDIT = "webcontent.edit"
WEBSITE_VIEW = "website.view"
WEBSITE_EDIT = "website.edit"
COMPETITIONS_VIEW = "competitions.view"
COMPETITIONS_EDIT = "competitions.edit"
RESULTS_VIEW = "results.view"
RESULTS_EDIT = "results.edit"
ENTRIES_VIEW = "entries.view"
ENTRIES_EDIT = "entries.edit"
CALLS_VIEW = "calls.view"
CALLS_EDIT = "calls.edit"
PEERING_VIEW = "peering.view"
PEERING_EDIT = "peering.edit"
UNITS_VIEW = "units.view"
UNITS_EDIT = "units.edit"
PLATFORM_EDIT = "platform.edit"
LOGINS_VIEW = "logins.view"
LOGINS_EDIT = "logins.edit"
EXPORT_LISTS = "export.lists"
EXPORT_FULL = "export.full"

ALL_TYPES = ("platform", "federation", "club", "unit")
MEMBER_TYPES = ("federation", "club")


@dataclass(frozen=True)
class Area:
    id: str
    label: str
    view_label: str
    edit_label: str = ""
    # Für welche Einheiten (Organization.type) der Bereich gilt
    org_types: tuple[str, ...] = MEMBER_TYPES
    # Stufen bei Rollen von Untereinheiten (leer: dort nicht vorhanden)
    dept_levels: tuple[str, ...] = ()
    # Abschaltbares Modul, zu dem der Bereich gehört
    module: str = ""
    # Name bei Rollen von Untereinheiten, z. B. „Mitglieder {gen}“ → „Mitglieder des Zugs“
    dept_label: str = ""

    @property
    def levels(self) -> tuple[str, ...]:
        return tuple(
            level for level, label in ((VIEW, self.view_label), (EDIT, self.edit_label)) if label
        )

    @property
    def view(self) -> str:
        return f"{self.id}.{VIEW}"

    @property
    def edit(self) -> str:
        return f"{self.id}.{EDIT}"


@dataclass(frozen=True)
class Extra:
    """Zusatzrecht: ein Häkchen, nur zusammen mit dem Leserecht von ``needs``."""

    code: str
    label: str
    needs: str
    org_types: tuple[str, ...] = MEMBER_TYPES
    dept: bool = False


_BOTH = (VIEW, EDIT)

AREAS: tuple[Area, ...] = (
    Area(
        "members",
        gettext_noop("Mitglieder"),
        gettext_noop("Liste, Akten, Ämter, Ehrungen, Würden und Jubiläen sehen"),
        gettext_noop("Mitglieder anlegen und ändern, Austritte, Import"),
        dept_levels=_BOTH,
        module="members",
        dept_label=gettext_noop("Mitglieder {gen}"),
    ),
    Area(
        "photos",
        gettext_noop("Fotos"),
        gettext_noop("Fotos der Mitglieder sehen"),
        gettext_noop("Fotos hochladen, Einwilligungen und Freigabelinks"),
        module="members",
    ),
    Area(
        "cards",
        gettext_noop("Mitgliedsausweise"),
        gettext_noop("Ausweise sehen und prüfen"),
        gettext_noop("Ausweise (QR-Code) erstellen und sperren"),
        dept_levels=_BOTH,
        module="members",
        dept_label=gettext_noop("Mitgliedsausweise {gen}"),
    ),
    Area(
        "logins",
        gettext_noop("Zugänge der Mitglieder"),
        gettext_noop("Sehen, wer einen Zugang hat"),
        gettext_noop("Anmeldelinks schicken und Zugänge beenden"),
        org_types=("club",),
        dept_levels=_BOTH,
        module="members",
    ),
    Area(
        "settings",
        gettext_noop("Einstellungen"),
        gettext_noop(
            "Organisationsdaten, Satzung, Mitgliedsarten, Zusatzfelder, Briefvorlage und "
            "Impressum sehen"
        ),
        gettext_noop("Organisationsdaten und {pl} bearbeiten"),
        org_types=("platform", "federation", "club"),
    ),
    Area(
        "theme",
        gettext_noop("Erscheinungsbild"),
        gettext_noop("Farben, Logo und Designs sehen"),
        gettext_noop("Erscheinungsbild ändern"),
        org_types=("platform", "federation", "club"),
    ),
    Area(
        "roles",
        gettext_noop("Rollen und Benutzer"),
        gettext_noop("Rollen, Rechte und Inhaber sehen"),
        gettext_noop("Rollen und Benutzer verwalten"),
        org_types=ALL_TYPES,
        dept_levels=_BOTH,
        dept_label=gettext_noop("Rollen {gen}"),
    ),
    Area(
        "todos",
        gettext_noop("Aufgaben"),
        gettext_noop("Eigene und mit mir geteilte Aufgaben"),
        gettext_noop("Aufgaben mit anderen teilen"),
        org_types=ALL_TYPES,
        dept_levels=_BOTH,
    ),
    Area(
        "material",
        gettext_noop("Material"),
        gettext_noop("Materialbestand und Zuordnungen sehen"),
        gettext_noop("Material, Standorte und Zuordnungen bearbeiten"),
        dept_levels=_BOTH,
        module="material",
    ),
    Area(
        "infrastructure",
        gettext_noop("Infrastruktur"),
        gettext_noop("Infrastruktur wie Schießstand oder Vereinsheim sehen"),
        gettext_noop("Infrastruktur, Bereiche und Zuordnungen bearbeiten"),
        dept_levels=_BOTH,
        module="infrastructure",
    ),
    Area(
        "bookings",
        gettext_noop("Belegung"),
        gettext_noop("Buchungskalender sehen und buchen"),
        gettext_noop("Buchungen für andere eintragen und freigeben"),
        dept_levels=_BOTH,
        # eines der beiden Module genügt
        module="material|infrastructure",
    ),
    Area(
        "audit",
        gettext_noop("Änderungsprotokoll"),
        gettext_noop("Änderungsprotokoll und Postausgang einsehen"),
        org_types=("platform", "federation", "club"),
    ),
    Area(
        "finance",
        gettext_noop("Kasse"),
        gettext_noop("Kasse, Belege und Berichte lesen (z. B. Kassenprüfer)"),
        gettext_noop("Kasse führen: Konten, Kategorien, Buchungen, Belege"),
        org_types=("federation", "club", "unit"),
        module="finance",
    ),
    Area(
        "billing",
        gettext_noop("Beiträge und Rechnungen"),
        gettext_noop("Beiträge, Rechnungen und Zahlungsstand lesen"),
        gettext_noop(
            "Beitragsregeln, Beitragsläufe, Rechnungen, Mahnungen und Zahlungen bearbeiten"
        ),
        org_types=("federation", "club", "unit"),
        dept_levels=(VIEW,),
        module="billing",
        dept_label=gettext_noop("Rechnungen {gen}"),
    ),
    Area(
        "music",
        gettext_noop("Musik"),
        gettext_noop("Musiker und Auftritte lesen"),
        gettext_noop("Musiker und Auftritte bearbeiten"),
        module="music",
    ),
    Area(
        "events",
        gettext_noop("Termine"),
        gettext_noop("Kalender, Rückmeldungen und Anhänge sehen"),
        gettext_noop("Termine verwalten: Kalender, Kategorien, öffentlicher Link"),
        dept_levels=_BOTH,
        module="events",
        dept_label=gettext_noop("Termine {gen}"),
    ),
    Area(
        "docs",
        gettext_noop("Dokumente"),
        gettext_noop("Dokumentenablage lesen"),
        gettext_noop("Dokumentenablage verwalten: Ordner, Dokumente, Freigaben"),
        dept_levels=_BOTH,
        dept_label=gettext_noop("Dokumente {gen}"),
    ),
    Area(
        "circulars",
        gettext_noop("Rundschreiben"),
        gettext_noop("Gesendete und empfangene Rundschreiben sehen"),
        gettext_noop("Rundschreiben verfassen und versenden (E-Mails und Serienbriefe)"),
        dept_levels=_BOTH,
        dept_label=gettext_noop("Rundschreiben {gen}"),
    ),
    Area(
        "webcontent",
        gettext_noop("Webseite: Inhalte"),
        gettext_noop("Texte und Bilder der Webseite sehen"),
        gettext_noop("Inhalte der Webseite bearbeiten (Texte und Bilder)"),
        org_types=("federation", "club", "unit"),
        module="website",
    ),
    Area(
        "website",
        gettext_noop("Webseite: Einrichtung"),
        gettext_noop("Zustand, Domains, Design und Bausteine sehen"),
        gettext_noop("Webseite einrichten: Zustand, Domains, Vorschau, Bausteine"),
        org_types=("federation", "club", "unit"),
        module="website",
    ),
    Area(
        "competitions",
        gettext_noop("Wettbewerbe"),
        gettext_noop("Wettbewerbe, Wertungen und Ranglisten sehen"),
        gettext_noop("Wettbewerbe verwalten: anlegen, Wertungen, abschließen, Auswertung"),
        module="competitions",
    ),
    Area(
        "results",
        gettext_noop("Ergebnisse"),
        gettext_noop("Starter und Ergebnisse sehen"),
        gettext_noop("Ergebnisse erfassen: Starter, Werte und Stechen (z. B. Schießmeister)"),
        module="competitions",
    ),
    Area(
        "entries",
        gettext_noop("Meldungen"),
        gettext_noop("Eigene Meldungen sehen"),
        gettext_noop("Meldungen an Veranstalter zusammenstellen und abgeben"),
        dept_levels=_BOTH,
        module="entries",
        dept_label=gettext_noop("Meldungen {gen}"),
    ),
    Area(
        "calls",
        gettext_noop("Ausschreibungen"),
        gettext_noop("Ausschreibungen an die Untereinheiten sehen"),
        gettext_noop("Ausschreibungen verwalten, Meldungen bestätigen"),
        module="entries",
    ),
    Area(
        "peering",
        gettext_noop("Verbund"),
        gettext_noop("Verbund mit anderen HUBIplan-Instanzen sehen"),
        gettext_noop("Verbund verwalten (Namen und Rechnungen nur zusammen mit den Rechten dafür)"),
        org_types=("platform", "federation", "club"),
    ),
    Area(
        "units",
        gettext_noop("{Pl}"),
        gettext_noop("{Pl} sehen"),
        gettext_noop("{Pl} anlegen und aus einer Exportdatei importieren"),
        org_types=("federation",),
    ),
    Area(
        "platform",
        gettext_noop("Plattform"),
        # Kein reines Lesen: Die Plattform zeigt Exporte und Postausgang aller Einheiten
        "",
        gettext_noop("Einheiten und Plattform verwalten"),
        org_types=("platform",),
    ),
)

EXTRAS: tuple[Extra, ...] = (
    Extra(
        EXPORT_LISTS,
        gettext_noop("Mitgliederlisten exportieren (Excel und PDF)"),
        "members",
        dept=True,
    ),
    Extra(
        EXPORT_FULL,
        gettext_noop("Vollständigen Datenexport und Auskunft nach DSGVO erstellen"),
        "settings",
    ),
    Extra(
        ROLES_PREVIEW,
        gettext_noop(
            "Ansicht als Rolle: HUBIplan so ansehen, wie eine Rolle es sieht (nur lesen, "
            "nie mehr als die eigenen Rechte)"
        ),
        "roles",
        org_types=ALL_TYPES,
    ),
)

AREA_BY_ID: dict[str, Area] = {a.id: a for a in AREAS}

# Abschaltbare Module (Organization.enabled_modules); ihre Bereiche fehlen, wenn aus
SWITCHABLE_MODULES: tuple[str, ...] = (
    "music",
    "material",
    "infrastructure",
    "members",
    "finance",
    "billing",
    "events",
    "website",
    "competitions",
    "entries",
)
# Module, die eine neue Einheit nicht automatisch bekommt (die Plattform schaltet
# sie gezielt frei, z. B. die Webseite nur für Einheiten, die eine haben sollen)
OPT_IN_MODULES: frozenset[str] = frozenset(
    {"website", "competitions", "entries", "material", "infrastructure", "music"}
)
DEFAULT_MODULES: tuple[str, ...] = tuple(m for m in SWITCHABLE_MODULES if m not in OPT_IN_MODULES)


def _area_codes(area: Area, levels: tuple[str, ...]) -> list[str]:
    return [f"{area.id}.{level}" for level in levels]


def codes_for(org_type: str) -> list[str]:
    """Alle Codes, die Rollen einer Einheit dieser Art haben können."""
    if org_type == "department":
        return sorted(DEPARTMENT_CODES)
    codes = [c for a in AREAS if org_type in a.org_types for c in _area_codes(a, a.levels)]
    codes += [e.code for e in EXTRAS if org_type in e.org_types]
    return codes


DEPARTMENT_CODES: frozenset[str] = frozenset(
    [c for a in AREAS if a.dept_levels for c in _area_codes(a, a.dept_levels)]
    + [e.code for e in EXTRAS if e.dept]
)
ALL_CODES: frozenset[str] = frozenset(c for t in ALL_TYPES for c in codes_for(t)) | DEPARTMENT_CODES

# --- Übergang: frühere Codes ↔ neue Codes ---

# Einheiten: früherer Code → neue Codes
LEGACY_TO_NEW: dict[str, tuple[str, ...]] = {
    MEMBERS_VIEW: ("members.view", PHOTOS_VIEW, CARDS_VIEW, LOGINS_VIEW),
    MEMBERS_EDIT: ("members.edit", LOGINS_EDIT),
    PHOTOS_MANAGE: ("photos.edit",),
    CARDS_MANAGE: ("cards.edit",),
    ORG_EDIT: (SETTINGS_EDIT,),
    AUDIT_VIEW: ("audit.view",),
    ROLES_MANAGE: (ROLES_EDIT,),
    ROLES_PREVIEW: (ROLES_PREVIEW, ROLES_VIEW),
    THEME_EDIT: ("theme.edit",),
    EXPORT_RUN: (EXPORT_LISTS,),
    DATA_EXPORT: (EXPORT_FULL,),
    FINANCE_VIEW: ("finance.view",),
    FINANCE_EDIT: ("finance.edit",),
    BILLING_VIEW: ("billing.view",),
    BILLING_EDIT: ("billing.edit",),
    EVENTS_MANAGE: (EVENTS_EDIT,),
    DOCS_VIEW: ("docs.view",),
    DOCS_MANAGE: (DOCS_EDIT,),
    CIRCULARS_SEND: (CIRCULARS_EDIT,),
    WEBSITE_CONTENT: (WEBCONTENT_EDIT,),
    WEBSITE_MANAGE: (WEBCONTENT_EDIT, WEBSITE_EDIT),
    COMPETITIONS_MANAGE: (COMPETITIONS_EDIT, RESULTS_EDIT),
    COMPETITIONS_RESULTS: (COMPETITIONS_VIEW, RESULTS_EDIT),
    ENTRIES_SUBMIT: (ENTRIES_EDIT,),
    ENTRIES_MANAGE: (CALLS_EDIT,),
    PEERING_MANAGE: (PEERING_EDIT,),
    CLUBS_MANAGE: (UNITS_EDIT,),
    PLATFORM_MANAGE: (PLATFORM_EDIT,),
}

# Untereinheiten: früherer Code → neue Codes
DEPT_LEGACY_TO_NEW: dict[str, tuple[str, ...]] = {
    DEPT_MEMBERS_VIEW: ("members.view",),
    DEPT_MEMBERS_EDIT: ("members.edit",),
    DEPT_ROLES_MANAGE: (ROLES_EDIT,),
    DEPT_ACCESS_MANAGE: (LOGINS_EDIT,),
    DEPT_EXPORT: (EXPORT_LISTS,),
    DEPT_INVOICES_VIEW: ("billing.view",),
    DEPT_CARDS_MANAGE: ("cards.edit",),
    DEPT_EVENTS_MANAGE: (EVENTS_EDIT,),
    DEPT_DOCS_MANAGE: (DOCS_EDIT,),
    DEPT_CIRCULARS_SEND: (CIRCULARS_EDIT,),
    DEPT_ENTRIES_SUBMIT: (ENTRIES_EDIT,),
}

# Neuer Code → früherer Code, den die bisherigen Prüfstellen erwarten
NEW_TO_LEGACY: dict[str, tuple[str, ...]] = {
    "members.view": (MEMBERS_VIEW,),
    "members.edit": (MEMBERS_EDIT,),
    "photos.edit": (PHOTOS_MANAGE,),
    "cards.edit": (CARDS_MANAGE,),
    SETTINGS_EDIT: (ORG_EDIT,),
    "audit.view": (AUDIT_VIEW,),
    ROLES_EDIT: (ROLES_MANAGE,),
    ROLES_PREVIEW: (ROLES_PREVIEW,),
    "theme.edit": (THEME_EDIT,),
    EXPORT_LISTS: (EXPORT_RUN,),
    EXPORT_FULL: (DATA_EXPORT,),
    "finance.view": (FINANCE_VIEW,),
    "finance.edit": (FINANCE_EDIT,),
    "billing.view": (BILLING_VIEW,),
    "billing.edit": (BILLING_EDIT,),
    EVENTS_EDIT: (EVENTS_MANAGE,),
    "docs.view": (DOCS_VIEW,),
    DOCS_EDIT: (DOCS_MANAGE,),
    CIRCULARS_EDIT: (CIRCULARS_SEND,),
    WEBCONTENT_EDIT: (WEBSITE_CONTENT,),
    WEBSITE_EDIT: (WEBSITE_MANAGE,),
    COMPETITIONS_EDIT: (COMPETITIONS_MANAGE,),
    RESULTS_EDIT: (COMPETITIONS_RESULTS,),
    ENTRIES_EDIT: (ENTRIES_SUBMIT,),
    CALLS_EDIT: (ENTRIES_MANAGE,),
    PEERING_EDIT: (PEERING_MANAGE,),
    UNITS_EDIT: (CLUBS_MANAGE,),
    PLATFORM_EDIT: (PLATFORM_MANAGE,),
}
DEPT_NEW_TO_LEGACY: dict[str, tuple[str, ...]] = {
    new: (old,) for old, news in DEPT_LEGACY_TO_NEW.items() for new in news
}

LEGACY_CODES: frozenset[str] = frozenset(LEGACY_TO_NEW) | frozenset(DEPT_LEGACY_TO_NEW)


def _translate(codes, table, keep) -> set[str]:
    result: set[str] = set()
    for code in codes or []:
        if not isinstance(code, str):
            continue
        if code in table and code not in keep:
            result.update(table[code])
        else:
            result.add(code)
    return result


def _complete(result: set[str]) -> list[str]:
    for code in list(result):
        area, _, level = code.rpartition(".")
        if level == EDIT and area in AREA_BY_ID and VIEW in AREA_BY_ID[area].levels:
            result.add(f"{area}.{VIEW}")
    for extra in EXTRAS:
        if extra.code in result:
            result.add(f"{extra.needs}.{VIEW}")
    return sorted(result)


def normalize(codes, *, dept: bool = False) -> list[str]:
    """Gespeicherte Form: nur frühere Codes übersetzt, ``edit`` zieht ``view`` mit.

    Codes, die alt und neu gleich heißen (z. B. ``members.view``), gelten als neu. Unbekannte
    Codes bleiben stehen (die Prüfung gegen den Katalog meldet sie).
    """
    table = DEPT_LEGACY_TO_NEW if dept else LEGACY_TO_NEW
    keep = DEPARTMENT_CODES if dept else ALL_CODES
    return _complete(_translate(codes, table, keep))


def from_legacy(codes, *, dept: bool = False) -> list[str]:
    """Rechte einer Rolle aus der Zeit vor den Bereichen vollständig übersetzen.

    Anders als ``normalize`` bekommt hier auch ``members.view`` Fotos und Ausweise dazu (so
    las die Rolle früher). Für Migration und alte Exportdateien.
    """
    table = DEPT_LEGACY_TO_NEW if dept else LEGACY_TO_NEW
    return _complete(_translate(codes, table, frozenset()))


def looks_legacy(codes, *, dept: bool = False) -> bool:
    """Enthält die Liste Codes, die es nur in der früheren Form gibt?"""
    table = DEPT_LEGACY_TO_NEW if dept else LEGACY_TO_NEW
    keep = DEPARTMENT_CODES if dept else ALL_CODES
    return any(isinstance(c, str) and c in table and c not in keep for c in codes or [])


def effective(codes, *, dept: bool = False) -> set[str]:
    """Wirksame Rechte: neue Codes und die daraus folgenden früheren Codes."""
    new = set(normalize(codes, dept=dept))
    table = DEPT_NEW_TO_LEGACY if dept else NEW_TO_LEGACY
    result = set(new)
    for code in new:
        result.update(table.get(code, ()))
    return result


def level_of(codes, area: str) -> str | None:
    """Stufe einer Rolle in einem Bereich: ``edit``, ``view`` oder None."""
    codes = set(codes or [])
    if f"{area}.{EDIT}" in codes:
        return EDIT
    if f"{area}.{VIEW}" in codes:
        return VIEW
    return None


def module_available(area: Area, org) -> bool:
    """Freigabe der Einheit; Untereinheiten bleiben an ihren Verein gebunden."""
    if not area.module or org is None:
        return True
    modules = set(area.module.split("|"))
    if not modules & set(org.enabled_modules or []):
        return False
    if org.type == "unit":
        owner = org.organization
        return owner is not None and bool(modules & set(owner.enabled_modules or []))
    return True


def enabled_codes_for(org, *, dept: bool = False) -> set[str]:
    """Konfigurierbare Codes, ohne abgeschaltete Bereiche und ihre Zusatzrechte."""
    allowed = set(codes_for("department" if dept else org.type))
    disabled = {a.id for a in AREAS if not module_available(a, org)}
    return {
        c
        for c in allowed
        if c.rpartition(".")[0] not in disabled
        and not any(e.code == c and e.needs in disabled for e in EXTRAS)
    }


def effective_for(codes, org, *, dept: bool = False) -> set[str]:
    """Freigaben vor dem Ergänzen alter Codes prüfen; gespeicherte Rechte bleiben bestehen."""
    active = set(normalize(codes, dept=dept)) & enabled_codes_for(org, dept=dept)
    return effective(active, dept=dept)


def preserve_disabled_permissions(value, stored, org, *, dept: bool = False) -> list[str]:
    """Nur sichtbare Rechte ändern, ruhende Rechte aus dem gespeicherten Stand behalten."""
    active = enabled_codes_for(org, dept=dept)
    return sorted(
        (set(normalize(value, dept=dept)) & active) | (set(normalize(stored, dept=dept)) - active)
    )


def catalog_for(org_type: str | None = None, org=None) -> list[dict]:
    """Katalog für die Rollenmaske: Bereiche mit Stufen, danach die Zusatzrechte.

    Die Beschriftungen enthalten Platzhalter wie ``{gen}`` oder ``{pl}`` (siehe
    ``organizations.terms``); ohne ``org`` gilt „Abteilung“. ``permissions`` listet die Codes
    wie früher (Lesen, Bearbeiten), damit ältere Oberflächen weiter funktionieren.
    """
    from organizations.terms import fill

    terms = org
    if org is None and org_type == "federation":
        from organizations.terms import default_terms_for

        terms = default_terms_for(org_type)
    dept = org_type == "department"
    result: list[dict] = []
    for a in AREAS:
        if dept:
            levels = a.dept_levels
        elif org_type is None or org_type in a.org_types:
            levels = a.levels
        else:
            levels = ()
        if not levels or not module_available(a, org):
            continue
        labels = {VIEW: a.view_label, EDIT: a.edit_label}
        entries = [
            {
                "code": f"{a.id}.{level}",
                "level": level,
                "label": fill(gettext(labels[level]), terms),
            }
            for level in levels
        ]
        label = a.dept_label if dept and a.dept_label else a.label
        result.append(
            {
                "id": a.id,
                "kind": "area",
                "module": a.module,
                "label": fill(gettext(label), terms),
                "levels": entries,
                "permissions": entries,
            }
        )
    extras = [
        {
            "code": e.code,
            "needs": f"{e.needs}.{VIEW}",
            "label": fill(gettext(e.label), terms),
        }
        for e in EXTRAS
        if (e.dept if dept else org_type is None or org_type in e.org_types)
        and module_available(AREA_BY_ID[e.needs], org)
    ]
    if extras:
        result.append(
            {
                "id": "extras",
                "kind": "extras",
                "module": "",
                "label": gettext("Zusatzrechte"),
                "levels": [],
                "permissions": extras,
            }
        )
    return result
