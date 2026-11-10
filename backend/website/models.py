"""Öffentliche Webseite einer Einheit (Daten und Regeln; die Darstellung liegt
im eigenen Repository ``hubiplan-website``).

Eine Einheit hat erst dann eine Webseite, wenn sie hier eingerichtet ist. Die
Webseite liest nur die öffentliche Schnittstelle ``/api/public/site/v1/…``.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from access.modules import MODULE_BY_ID, module_on

from .designs import DEFAULT_DESIGN, DESIGNS

# Bausteine, die sich auf der Webseite einzeln ein- und ausschalten lassen.
# Name und Reihenfolge wie im Menü der Webseite; „units“ trägt in der Verwaltung
# die eigene Bezeichnung der Einheit (z. B. „Züge“).
BLOCKS = {
    "posts": "Aktuelles",
    "events": "Termine",
    "board": "Vorstand",
    "members": "Mitglieder",
    "memorial": "In Gedenken",
    "units": "Untereinheiten",
    "honors": "Majestäten",
    "results": "Ergebnisse",
    "gallery": "Galerie",
    "history": "Chronik",
    "offices": "Ämter",
    "repertoire": "Repertoire",
    "press": "Presse",
    "bookings": "Belegung",
    "statutes": "Dokumente",
    "contact": "Kontakt",
    "social": "Social-Media-Symbole",
    "search": "Suche",
}
BLOCK_HINTS = {
    "posts": "Beiträge aus Instagram und Facebook (lokal gespeichert)",
    "events": "mit Kalender-Abo",
    "board": "Vorstand und Ansprechpartner",
    "members": "Überschrift mit den Mitgliederlisten je Mitgliedsart",
    "memorial": "verstorbene Mitglieder mit Todesjahr; Einleitung unter Webseite › Texte",
    "units": "Seiten der Untereinheiten",
    "honors": "aktuelle und frühere Würdenträger",
    "results": "Wettbewerbe mit „auf der Webseite“, Reihen und Wanderpokale",
    "gallery": "Fotoalben unter Webseite › Galerie",
    "history": "Textseite zur Geschichte des Vereins (Webseite › Texte)",
    "offices": "heutige und frühere Inhaber der Rollen mit „unter Ämter zeigen“",
    "repertoire": "Stücke aus dem Notenarchiv mit „im Repertoire auf der Webseite“",
    "press": "Pressespiegel: Zeitungsartikel als PDF oder Bild (Webseite › Dokumente)",
    "bookings": "Infrastruktur und Material, deren Buchungskalender „auf der Webseite“ zeigt",
    "statutes": "Satzung, Beitragsordnung, Gründungsurkunde und eigene Dokumente",
    "contact": "Kontaktformular",
    "social": "oben im Kopf, auf dem Handy im Menü",
    "search": "Lupe im Menü: sucht in Textseiten, Terminen und Alben",
}
# Neue Bereiche, die erst nach dem Einschalten erscheinen (die Galerie, Ralf 05.11.)
# Mitgliederlisten, Gedenken und Suche (Ralf 05.11., Kapelle) ebenso
DEFAULT_OFF_BLOCKS = {
    "gallery",
    "members",
    "memorial",
    "search",
    "repertoire",
    "press",
    "bookings",
}
DEFAULT_BLOCKS = {key: key not in DEFAULT_OFF_BLOCKS for key in BLOCKS}
# Bausteine, die ein Modul brauchen (access/modules.py); bei abgeschaltetem Modul
# erscheinen sie weder auf der Webseite noch in den Einstellungen
BLOCK_MODULES = {
    "events": "events",
    "bookings": "bookings",
    "honors": "honors",
    "honorary": "awards",
    "results": "competitions",
    "repertoire": "scores",
    "history": "chronicle",
    "posts": "social",
}
# Menüpunkte unter „Würdenträger“, die sich einzeln ausschalten lassen (Ralf 2026-10-31):
# ``dignity:<Nummer>`` je Würde und ``honorary`` für die Ehrungen. Ohne Eintrag: an.
# Dazu ``membertype:<Nummer>`` je Mitgliedsart unter „Mitglieder“ (Ralf 05.11.); ohne
# Eintrag aus, denn eine Liste aller Mitglieder erscheint nur nach bewusstem Einschalten.
EXTRA_BLOCK = re.compile(r"^(dignity:[1-9][0-9]{0,9}|honorary|membertype:[1-9][0-9]{0,9})$")
DEFAULT_OFF_PREFIXES = ("membertype:",)
# Frei benannte Überschriften im Menü (Ralf 05.11.): ``heading:<Nummer>``, Name in
# ``block_names``; ohne Namen gibt es die Überschrift nicht.
HEADING_KEY = re.compile(r"^heading:[1-9][0-9]{0,2}$")
# Links nach außen im Menü (Ralf 10.11., Konzept webseite-baukasten G0): ``link:<Nummer>``,
# Name in ``block_names``, Adresse in ``menu_links``; ohne Name oder Adresse gibt es ihn nicht.
LINK_KEY = re.compile(r"^link:[1-9][0-9]{0,2}$")
LINK_URL_MAX = 300


def block_module(key: str) -> str | None:
    """Modul, das ein Baustein braucht (Würden ``dignity:<Nummer>``: Würden)."""
    if isinstance(key, str) and key.startswith("dignity:"):
        return "honors"
    return BLOCK_MODULES.get(key)


def _off(org, modules: dict[str, str]) -> set[str]:
    return {k for k, m in modules.items() if m in MODULE_BY_ID and not module_on(org, m)}


def blocks_without_module(org) -> set[str]:
    """Bausteine, deren Modul für diese Einheit abgeschaltet ist."""
    return _off(org, BLOCK_MODULES)


def home_without_module(org) -> set[str]:
    """Bausteine der Startseite, deren Modul für diese Einheit abgeschaltet ist."""
    return _off(org, HOME_MODULES)


def is_extra_block(key) -> bool:
    return isinstance(key, str) and bool(EXTRA_BLOCK.match(key))


def is_heading_key(key) -> bool:
    return isinstance(key, str) and bool(HEADING_KEY.match(key))


def is_link_key(key) -> bool:
    return isinstance(key, str) and bool(LINK_KEY.match(key))


# Eigene Namen der Bausteine (Ralf 2026-11-01): erscheinen im Menü und als Überschrift
# auf der Webseite; leer = Standardname. Umbenennbar sind die Bausteine (ohne „social“),
# die Überschrift „Geschichte“ und die Ehrungen. Würden und Textseiten tragen ihren
# Namen schon selbst.
RENAMABLE_BLOCKS = tuple(k for k in BLOCKS if k not in ("social", "search")) + (
    "group:history",
    "honorary",
)
BLOCK_NAME_MAX = 60
MEMBERTYPE_KEY = re.compile(r"^membertype:[1-9][0-9]{0,9}$")


def is_renamable(key) -> bool:
    """Feste Bausteine, Listen je Mitgliedsart und freie Überschriften."""
    return isinstance(key, str) and (
        key in RENAMABLE_BLOCKS
        or bool(MEMBERTYPE_KEY.match(key))
        or is_heading_key(key)
        or is_link_key(key)
    )


# Bausteine der Startseite: ein- und ausschaltbar, Reihenfolge frei. Die
# Standardliste entspricht der Startseite vor der freien Zusammenstellung.
HOME_SECTIONS = {
    "carousel": "Bilderkarussell",
    "greeting": "Willkommenstext",
    "events": "Nächste Termine",
    "honors": "Majestäten",
    "units": "Untereinheiten",
    "results": "Aktuelle Ergebnisse",
    "instagram": "Instagram-Beiträge",
    "facebook": "Facebook-Beiträge",
}
HOME_HINTS = {
    "carousel": "Fotos zum Willkommenstext; bei einem Foto das Titelbild",
    "greeting": "Überschrift und Text unter Webseite › Texte",
    "events": "die nächsten drei öffentlichen Termine",
    "honors": "die aktuellen Majestäten",
    "units": "Kacheln mit Links zu den Seiten der Untereinheiten",
    "results": "die neuesten Wettbewerbe mit den Siegern, live mit Zwischenstand",
    "instagram": "neueste Beiträge, sobald ein Kanal verbunden ist",
    "facebook": "neueste Beiträge, sobald ein Kanal verbunden ist",
}
# Bausteine der Startseite, die ein Modul brauchen
HOME_MODULES = {
    "events": "events",
    "honors": "honors",
    "results": "competitions",
    "instagram": "social",
    "facebook": "social",
}
# Welcher Bereich der Webseite eingeschaltet sein muss, damit der Baustein erscheint
HOME_NEEDS_BLOCK = {"events": "events", "honors": "honors", "units": "units", "results": "results"}
# „Aktuelle Ergebnisse“ ist ein möglicher Block (Ralf 01.11.): erst an, wenn gewählt
DEFAULT_HOME_OFF = {"instagram", "facebook", "results"}


def default_home_sections() -> list:
    return [{"key": k, "on": k not in DEFAULT_HOME_OFF} for k in HOME_SECTIONS]


def normalize_home_sections(value) -> list:
    """Gespeicherte Liste → vollständige Liste in Reihenfolge (neue Bausteine hinten).

    Dazu die eigenen Abschnitte (G3) und je Eintrag Hintergrund, Breite und Spalte."""
    from .home import normalize

    return normalize(value, HOME_SECTIONS, DEFAULT_HOME_OFF)


# Was der Entwurf der Gestaltung umfasst (Design, Farbrollen, Stilregler, Kopfbild, Startseite)
DRAFT_FIELDS = ("design", "color_roles", "style", "header_image", "home_sections", "layouts")
DESIGN_VERSIONS = 5  # wie bei den Texten: die letzten 5 veröffentlichten Fassungen


def default_blocks() -> dict:
    return dict(DEFAULT_BLOCKS)


class Website(models.Model):
    """Eingerichtete Webseite einer Einheit (höchstens eine je Einheit)."""

    class State(models.TextChoices):
        OFF = "off", gettext_lazy("Aus")
        MAINTENANCE = "maintenance", gettext_lazy("Wartung")
        PUBLIC = "public", gettext_lazy("Öffentlich")

    class NameFormat(models.TextChoices):
        FULL = "full", gettext_lazy("Vorname Name")
        INITIAL = "initial", gettext_lazy("Vorname N.")

    class MissingConsent(models.TextChoices):
        OMIT = "omit", gettext_lazy("auslassen")
        NN = "nn", gettext_lazy("als „N. N.“ zeigen")

    class Units(models.TextChoices):
        ALL = "all", gettext_lazy("alle")
        SELECTED = "selected", gettext_lazy("ausgewählte")
        NONE = "none", gettext_lazy("keine")

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="site"
    )
    state = models.CharField(
        "Zustand", max_length=12, choices=State.choices, default=State.MAINTENANCE
    )
    maintenance_text = models.TextField(
        "Hinweis auf der Wartungsseite",
        max_length=1000,
        blank=True,
        default="Hier entsteht unsere neue Webseite.",
    )
    # Kennung der Webseite in der öffentlichen Schnittstelle (kein Geheimnis,
    # aber ohne fortlaufende Nummern)
    public_key = models.CharField(max_length=40, unique=True)
    blocks = models.JSONField("Bausteine", default=default_blocks, blank=True)
    # Anordnung des Menüs (Reihenfolge, Unterpunkte); leer = Standard (website/menu.py)
    menu = models.JSONField("Menü", default=list, blank=True)
    # Eigene Namen der Bausteine: Schlüssel → Name (nur gesetzte; RENAMABLE_BLOCKS)
    block_names = models.JSONField("Eigene Namen der Bausteine", default=dict, blank=True)
    # Adressen der Links nach außen im Menü: ``link:<Nummer>`` → https://…
    menu_links = models.JSONField("Links im Menü", default=dict, blank=True)
    # Ein Hauptpunkt des Menüs als Knopf hervorgehoben (z. B. „Mitglied werden“), leer = keiner
    menu_button = models.CharField("Menüpunkt als Knopf", max_length=40, blank=True)
    # Stilregler (Gestaltung › Feinabstimmung, website/style.py): nur verstellte; leer = Design
    style = models.JSONField("Stilregler", default=dict, blank=True)
    # Darstellung der festen Bereiche (G5, website/variants.py): nur abweichende Varianten
    layouts = models.JSONField("Darstellung der Bereiche", default=dict, blank=True)
    home_sections = models.JSONField(
        "Bausteine der Startseite", default=default_home_sections, blank=True
    )
    # Hinweisleiste oben auf allen Seiten (G6), z. B. „Schützenfest 22.–25.8.: Programm“;
    # erscheint nur im Zeitraum und verschwindet danach von selbst. Ziel wie bei Knöpfen
    notice_text = models.CharField(
        "Hinweisleiste", max_length=200, blank=True, default="", db_default=""
    )
    notice_target = models.JSONField(
        "Ziel der Hinweisleiste", default=dict, blank=True, db_default={}
    )
    notice_from = models.DateField("Hinweisleiste ab", null=True, blank=True)
    notice_until = models.DateField("Hinweisleiste bis", null=True, blank=True)
    # Entwurf der Gestaltung (Konzept webseite-baukasten G2): nur geänderte Felder aus
    # DRAFT_FIELDS; sichtbar nur in der Vorschau, bis jemand „Veröffentlichen“ wählt
    draft = models.JSONField("Entwurf der Gestaltung", default=dict, blank=True)
    # Standarddesign der Webseite und eigene Farbzuordnung je Design (Ralf 2026-10-31).
    # Auch der Schlüssel eines freigegebenen Designpakets (DesignPackage, Ralf 2026-11-02);
    # geprüft wird im Code (design_choices), nicht über feste choices.
    design = models.CharField("Design", max_length=40, default=DEFAULT_DESIGN)
    # Galerie (Ralf 05.11.): Reihenfolge der Alben auf der Galerie-Seite
    gallery_order = models.CharField(
        "Alben sortieren nach", max_length=20, default="date_desc", blank=True
    )
    color_roles = models.JSONField("Farbzuordnung je Design", default=dict, blank=True)
    name_format = models.CharField(
        "Namensform", max_length=10, choices=NameFormat.choices, default=NameFormat.FULL
    )
    show_vacant = models.BooleanField(
        "unbesetzte Funktionen als „derzeit unbesetzt“ zeigen", default=False
    )
    # Kapelle (Ralf 05.11.): Hauptinstrument aus dem Musikmodul unter dem Namen, Anschrift
    # beim Vorstand nur mit Einwilligung der Person und diesem Schalter
    show_instrument = models.BooleanField(
        "Hauptinstrument unter dem Namen zeigen", default=False, db_default=False
    )
    show_address = models.BooleanField(
        "Anschrift beim Vorstand zeigen (nur mit Einwilligung)", default=False, db_default=False
    )
    show_member_since = models.BooleanField(
        "Mitgliederlisten mit Eintrittsjahr", default=True, db_default=True
    )
    missing_consent = models.CharField(
        "Personen ohne Einwilligung",
        max_length=10,
        choices=MissingConsent.choices,
        default=MissingConsent.OMIT,
    )
    units_mode = models.CharField(
        "Untereinheiten", max_length=10, choices=Units.choices, default=Units.ALL
    )
    unit_ids = models.JSONField("ausgewählte Untereinheiten", default=list, blank=True)
    include_unit_events = models.BooleanField(
        "Termine der Untereinheiten im Kalender der Webseite", default=True
    )
    include_parent_events = models.BooleanField(
        "Termine der übergeordneten Einheiten im Kalender der Webseite", default=False
    )
    include_parent_honors = models.BooleanField(
        "weitergegebene Würden der übergeordneten Einheiten zeigen", default=False
    )
    allow_indexing = models.BooleanField("Suchmaschinen erlauben", default=True)
    # Sprache der festen Texte auf der Webseite (konzepte/englisch.md, W1); Vereinsdaten
    # bleiben, wie sie sind
    language = models.CharField(
        "Sprache der Webseite", max_length=8, choices=settings.LANGUAGES, default="de"
    )
    contact_limit_per_hour = models.PositiveSmallIntegerField(
        "höchstens Formularmails je Stunde", default=20
    )
    # Datenschutzhinweise der Webseite (eigener Text, getrennt von denen für Mitglieder)
    privacy_mode = models.CharField(
        "Datenschutzhinweise der Webseite",
        max_length=10,
        choices=[("text", "eigener Text"), ("link", "auf eigene Seite verlinken")],
        default="text",
    )
    # Entwurf; öffentlich gilt die veröffentlichte Fassung (UI-Audit 29.10. NAF-02)
    privacy_text = models.TextField("Entwurf der Datenschutzhinweise", max_length=30000, blank=True)
    privacy_published_text = models.TextField(
        "Veröffentlichte Datenschutzhinweise", max_length=30000, blank=True
    )
    privacy_published_at = models.DateTimeField(
        "Datenschutzhinweise veröffentlicht am", null=True, blank=True
    )
    privacy_url = models.URLField("Adresse der Datenschutzhinweise", blank=True)
    # Stand der Einstellungen bei der letzten Erzeugung (Hinweis „passt nicht mehr“)
    privacy_facts = models.CharField(max_length=64, blank=True)
    privacy_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Der Entwurf ändert sich bei jedem Klick; protokolliert wird das Veröffentlichen
    derived_fields = ("draft",)

    class Meta:
        verbose_name = "Webseite"
        verbose_name_plural = "Webseiten"

    def __str__(self) -> str:
        return f"Webseite ({self.get_state_display()})"

    @staticmethod
    def new_key() -> str:
        return secrets.token_urlsafe(18)

    def packages(self):
        """Für diese Webseite freigegebene Designpakete."""
        # Legacy free templates remain stored for administrators, but are quarantined
        # from all public clients, including older website versions.
        return [
            p for p in self.design_packages.all() if not p.templates and p.sketch_like in DESIGNS
        ]

    def apply_draft(self) -> None:
        """Entwurf nur im Speicher über die Werte legen (Vorschau); nie danach speichern."""
        draft = self.draft if isinstance(self.draft, dict) else {}
        for key in DRAFT_FIELDS:
            if key in draft and key != "header_image":
                setattr(self, key, draft[key])
        if "header_image" in draft:
            self.draft_header_image = draft["header_image"]

    def design_choices(self) -> set[str]:
        return set(DESIGNS) | {p.key for p in self.packages()}

    def effective_design(self) -> str:
        """Gewähltes Design; fehlt das Paket oder seine Freigabe, Klassisch."""
        return self.design if self.design in self.design_choices() else DEFAULT_DESIGN

    def block_on(self, key: str) -> bool:
        # Baustein eines abgeschalteten Moduls erscheint nicht (module-neustruktur)
        module = block_module(key)
        if module in MODULE_BY_ID and not module_on(self.organization, module):
            return False
        if is_extra_block(key):
            default = not key.startswith(DEFAULT_OFF_PREFIXES)
        else:
            default = DEFAULT_BLOCKS.get(key, False)
        return bool((self.blocks or {}).get(key, default))

    def block_name(self, key: str) -> str:
        """Eigener Name eines Bausteins oder leer (dann gilt der Standardname)."""
        name = (self.block_names or {}).get(key) if is_renamable(key) else None
        return name.strip() if isinstance(name, str) else ""

    def names(self) -> dict[str, str]:
        """Alle gesetzten eigenen Namen (für die öffentliche Schnittstelle)."""
        keys = [
            *RENAMABLE_BLOCKS,
            *(k for k in self.block_names or {} if k not in RENAMABLE_BLOCKS),
        ]
        return {k: n for k in keys if (n := self.block_name(k))}

    def headings(self) -> dict[str, str]:
        """Freie Überschriften im Menü: Schlüssel → Name, in Reihenfolge der Nummer."""
        found = {k: self.block_name(k) for k in self.block_names or {} if is_heading_key(k)}
        return {k: found[k] for k in sorted(found, key=lambda k: int(k.split(":")[1])) if found[k]}

    def links(self) -> dict[str, tuple[str, str]]:
        """Links nach außen im Menü: Schlüssel → (Name, Adresse), in Reihenfolge der Nummer."""
        urls = self.menu_links if isinstance(self.menu_links, dict) else {}
        found = {}
        for key in self.block_names or {}:
            url = urls.get(key)
            if is_link_key(key) and isinstance(url, str) and url and (name := self.block_name(key)):
                found[key] = (name, url)
        return {k: found[k] for k in sorted(found, key=lambda k: int(k.split(":")[1]))}

    def home(self) -> list[str]:
        """Eingeschaltete Bausteine der Startseite in ihrer Reihenfolge."""
        keys = []
        for s in normalize_home_sections(self.home_sections):
            if "kind" in s:
                continue  # eigene Abschnitte (G3) stehen nur in ``home_layout``
            needs = HOME_NEEDS_BLOCK.get(s["key"])
            if s["on"] and (needs is None or self.block_on(needs)):
                keys.append(s["key"])
        return keys

    def clean(self):
        unknown = {k for k in self.blocks or {} if k not in BLOCKS and not is_extra_block(k)}
        if unknown:
            raise ValidationError(
                {"blocks": gettext("Unbekannter Baustein: {x0}").format(x0=sorted(unknown)[0])}
            )
        if not 1 <= (self.contact_limit_per_hour or 0) <= 100:
            raise ValidationError(
                {"contact_limit_per_hour": gettext("Bitte einen Wert zwischen 1 und 100 angeben.")}
            )
        if self.notice_from and self.notice_until and self.notice_until < self.notice_from:
            raise ValidationError({"notice_until": gettext("Das Ende liegt vor dem Anfang.")})

    def notice_active(self, today: datetime.date | None = None) -> bool:
        """Hinweisleiste (G6) zeigen: Text da und heute im Zeitraum (Grenzen eingeschlossen)."""
        today = today or timezone.localdate()
        return bool(self.notice_text.strip()) and (
            (self.notice_from is None or self.notice_from <= today)
            and (self.notice_until is None or today <= self.notice_until)
        )


HOSTNAME_RE = r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"


class DesignPackage(models.Model):
    """Eingespieltes Design (Paket aus design_packages.py), nicht im Repository.

    Gilt für die ganze Installation; wählen können es nur freigegebene Webseiten.
    Einspielen, Freigeben und Löschen dürfen nur Plattformverwalter (Ralf 2026-11-02).
    """

    key = models.CharField("Kürzel", max_length=40, unique=True)
    label = models.CharField("Name", max_length=60)
    label_en = models.CharField("Name (Englisch)", max_length=60, blank=True)
    hint = models.CharField("Beschreibung", max_length=300, blank=True)
    hint_en = models.CharField("Beschreibung (Englisch)", max_length=300, blank=True)
    roles = models.JSONField("Farbrollen", default=dict)
    sketch_like = models.CharField("Skizze wie", max_length=20, default=DEFAULT_DESIGN)
    css = models.TextField("Gestaltung (CSS)", blank=True)
    templates = models.JSONField("Vorlagen", default=dict, blank=True)
    content_hash = models.CharField("Prüfsumme", max_length=64)
    websites = models.ManyToManyField(
        Website, blank=True, related_name="design_packages", verbose_name="freigegeben für"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["label", "key"]
        verbose_name = "Designpaket"
        verbose_name_plural = "Designpakete"

    def __str__(self) -> str:
        return self.label

    def label_for(self, language: str) -> str:
        return (self.label_en if language == "en" and self.label_en else "") or self.label

    def hint_for(self, language: str) -> str:
        return (self.hint_en if language == "en" and self.hint_en else "") or self.hint


class WebsiteDomain(models.Model):
    """Hostname, unter dem die Webseite erreichbar ist (die Webseite erkennt daran
    die Einheit)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField("Domain", max_length=253, unique=True)
    is_primary = models.BooleanField("Hauptadresse", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Domain der Webseite"
        verbose_name_plural = "Domains der Webseite"
        ordering = ["-is_primary", "hostname"]

    def __str__(self) -> str:
        return self.hostname


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


PREVIEW_LINK_MAX_DAYS = 14


class PreviewLink(models.Model):
    """Zeitlich begrenzter, widerrufbarer Vorschau-Link zum Weitergeben."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="preview_links")
    label = models.CharField("Bezeichnung", max_length=100, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField("gültig bis")
    revoked_at = models.DateTimeField("widerrufen am", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vorschau-Link"
        verbose_name_plural = "Vorschau-Links"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Vorschau-Link {self.label}".strip()

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()

    @classmethod
    def create(cls, website: Website, days: int, label: str, user) -> tuple[PreviewLink, str]:
        token = secrets.token_urlsafe(24)
        link = cls.objects.create(
            organization=website.organization,
            website=website,
            label=label,
            token_hash=hash_token(token),
            expires_at=timezone.now() + datetime.timedelta(days=days),
            created_by=user,
        )
        return link, token


class DesignVersion(models.Model):
    """Veröffentlichte Gestaltung (Werte aus DRAFT_FIELDS), die letzten fünf bleiben."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="design_versions")
    data = models.JSONField(default=dict)
    published_at = models.DateTimeField(default=timezone.now)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Fassung der Gestaltung"
        verbose_name_plural = "Fassungen der Gestaltung"
        ordering = ["-published_at", "-pk"]

    def __str__(self) -> str:
        return f"Gestaltung vom {timezone.localtime(self.published_at):%d.%m.%Y %H:%M}"


class PublicationConsent(models.Model):
    """Einwilligung bzw. Widerspruch eines Mitglieds zur Veröffentlichung.

    Je Kategorie gilt höchstens ein Eintrag ohne Enddatum. Endet ein Eintrag
    (Widerruf der Einwilligung, Rücknahme des Widerspruchs), bleibt er als
    Verlauf erhalten.
    """

    class Category(models.TextChoices):
        NAME = "name", gettext_lazy("Name mit Funktion")
        PHOTO = "photo", gettext_lazy("Foto")
        EMAIL = "email", gettext_lazy("E-Mail-Adresse")
        PHONE = "phone", gettext_lazy("Telefonnummer")
        ADDRESS = "address", gettext_lazy("Anschrift")
        HONORS = "honors", gettext_lazy("Würden und Chronik")
        JUBILEES = "jubilees", gettext_lazy("Jubiläen")
        RESULTS = "results", gettext_lazy("Wettbewerbsergebnisse")
        RESULTS_MINOR = "minor_res", gettext_lazy("Wettbewerbsergebnisse unter 18")
        # Gesamtaudit 05.11. F-01: Mitgliederlisten nur mit Einwilligung; „In Gedenken“
        # nur mit Freigabe des Vorstands je Person (oder Einwilligung zu Lebzeiten)
        MEMBER_LIST = "list", gettext_lazy("Mitgliederliste")
        MEMORIAL = "memorial", gettext_lazy("In Gedenken")

    class Source(models.TextChoices):
        BOARD = "board", gettext_lazy("Vorstand")
        MEMBER = "member", gettext_lazy("Mitglied selbst")
        PAPER = "paper", gettext_lazy("Papierformular")

    # Name und Würden erscheinen aus berechtigtem Interesse, solange kein
    # Widerspruch vorliegt; alles andere nur mit Einwilligung.
    # Wettbewerbsergebnisse ebenso (Teilnahme an einem öffentlichen Wettbewerb); unter 18
    # nur mit ausdrücklicher Einwilligung (Kategorie „Wettbewerbsergebnisse unter 18“)
    OBJECTION_CATEGORIES = frozenset({Category.NAME, Category.HONORS, Category.RESULTS})

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey(
        "members.Membership", on_delete=models.CASCADE, related_name="publication_consents"
    )
    category = models.CharField("Kategorie", max_length=10, choices=Category.choices)
    since = models.DateField("seit")
    source = models.CharField("erfasst durch", max_length=10, choices=Source.choices)
    ended_at = models.DateField("beendet am", null=True, blank=True)
    ended_source = models.CharField(
        "beendet durch", max_length=10, choices=Source.choices, blank=True
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Veröffentlichung (Einwilligung/Widerspruch)"
        verbose_name_plural = "Veröffentlichung (Einwilligungen/Widersprüche)"
        ordering = ["category", "-since", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "category"],
                condition=models.Q(ended_at__isnull=True),
                name="veroeffentlichung_einmal_aktiv",
            )
        ]

    def __str__(self) -> str:
        kind = "Widerspruch" if self.is_objection else "Einwilligung"
        return f"{kind}: {self.get_category_display()}"

    @property
    def is_objection(self) -> bool:
        return self.category in self.OBJECTION_CATEGORIES


from .contact_models import HeldMessage  # noqa: E402, F401
from .content_models import (  # noqa: E402, F401
    GalleryAlbum,
    GalleryItem,
    WebsiteDocument,
    WebsiteImage,
    WebsiteRevision,
    WebsiteText,
)
from .social_models import SocialFeed, SocialPost, SocialPostImage  # noqa: E402, F401
