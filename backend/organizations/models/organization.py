"""Einheiten: Organisation, Untereinheit und deren Rollen."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from access.models import Role

from .fields import (
    DEFAULT_CHILD_LABELS,
    DEFAULT_LABELS,
    SHORT_NAME_MAX,
    WORKSPACE_MODULES,
    DatePrecision,
    FiscalYearFields,
    ShortNameMixin,
    ThemeFields,
    default_jubilee_years,
    default_unit_jubilee_years,
    founding_year_validators,
    homepage_image_path,
)


class Organization(ShortNameMixin, FiscalYearFields, ThemeFields):
    class Type(models.TextChoices):
        PLATFORM = "platform", gettext_lazy("Plattform")
        FEDERATION = "federation", gettext_lazy("Dachverband")
        CLUB = "club", gettext_lazy("Verein")
        UNIT = "unit", gettext_lazy("Untereinheit")

    class MemberAccess(models.TextChoices):
        NONE = "none", gettext_lazy("kein Zugriff")
        READ = "read", gettext_lazy("nur lesen")
        WRITE = "write", gettext_lazy("lesen und ändern")

    class CancellationEnd(models.TextChoices):
        """Zu welchem Termin eine Kündigung des Mitglieds wirkt (Satzung)."""

        ANY = "any", gettext_lazy("zu jedem Tag")
        MONTH = "month", gettext_lazy("zum Monatsende")
        QUARTER = "quarter", gettext_lazy("zum Quartalsende")
        HALF_YEAR = "half_year", gettext_lazy("zum Halbjahresende")
        YEAR = "year", gettext_lazy("zum Ende des Geschäftsjahres")

    class ContactSource(models.TextChoices):
        OWN = "own", gettext_lazy("eigene Angaben")
        ROLE = "role", gettext_lazy("von einer Vorstandsrolle übernehmen")

    type = models.CharField("Art", max_length=20, choices=Type.choices)
    # Feste Kennung, auch über Instanzen hinweg (Verbund) und beim Umzug unverändert
    uuid = models.UUIDField("feste Kennung", default=uuid.uuid4, unique=True, editable=False)
    parent = models.ForeignKey(
        "self",
        verbose_name="übergeordnete Organisation",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    # Einheit mit dem Datenbereich, zu dem eine Untereinheit gehört (bei
    # Einheiten mit eigenem Datenbereich leer)
    organization = models.ForeignKey(
        "self",
        verbose_name="Datenbereich",
        on_delete=models.CASCADE,
        related_name="departments",
        null=True,
        blank=True,
    )
    name = models.CharField("Name", max_length=200)
    short_name = models.CharField(
        "Kurzname",
        max_length=SHORT_NAME_MAX,
        blank=True,
        help_text="Optional, für Navigation, Listen und Auswahlfelder.",
    )
    # Dachverband: Grammatik seines Namens in den Texten seiner Vereine
    name_gender = models.CharField(
        "Artikel des Namens",
        max_length=1,
        choices=[("f", "die (weiblich)"), ("m", "der (männlich)"), ("n", "das (sächlich)")],
        default="m",
        help_text="Für Texte der Vereine, z. B. „an den BSV melden“.",
    )
    name_genitive = models.CharField(
        "Name im Genitiv, falls abweichend",
        max_length=200,
        blank=True,
        help_text="Leer: Der Name bleibt unverändert (des BSV).",
    )
    founding_year = models.PositiveSmallIntegerField(
        "Gründungsjahr", null=True, blank=True, validators=founding_year_validators()
    )
    sort_order = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    # Bezeichnung der Einheit selbst (z. B. „Verein“, „Zug“), mit Grammatik
    label = models.CharField("Bezeichnung (Einzahl)", max_length=50, blank=True)
    label_plural = models.CharField("Bezeichnung (Mehrzahl)", max_length=50, blank=True)
    label_gender = models.CharField(
        "Bezeichnung (Genus)",
        max_length=1,
        choices=[("f", "die (weiblich)"), ("m", "der (männlich)"), ("n", "das (sächlich)")],
        default="m",
    )
    label_genitive = models.CharField(
        "Bezeichnung (Genitiv, falls abweichend)", max_length=50, blank=True
    )
    # Englische Bezeichnung (Konzept englisch.md, F7); leer: Vorgabe bzw. die deutsche
    label_en = models.CharField(
        "Bezeichnung englisch (Einzahl)", max_length=50, blank=True, default="", db_default=""
    )
    label_plural_en = models.CharField(
        "Bezeichnung englisch (Mehrzahl)", max_length=50, blank=True, default="", db_default=""
    )
    street = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    address_extra = models.CharField(
        "Adresszusatz",
        max_length=200,
        blank=True,
        default="",
        db_default="",
        help_text="z. B. c/o Firma oder Gebäude; steht über Straße und Hausnummer.",
    )
    postal_code = models.CharField("PLZ", max_length=10, blank=True)
    city = models.CharField("Ort", max_length=100, blank=True)
    country = models.CharField("Land", max_length=100, blank=True, default="Deutschland")

    contact_source = models.CharField(
        "Kontaktdaten", max_length=10, choices=ContactSource.choices, default=ContactSource.OWN
    )
    contact_role = models.ForeignKey(
        "access.Role",
        verbose_name="Kontakt-Rolle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Die Kontaktdaten kommen von der Person, die diese Rolle gerade innehat.",
    )
    contact_email = models.EmailField("E-Mail", blank=True)
    contact_phone = models.CharField("Telefon", max_length=50, blank=True)
    website = models.URLField("Website", blank=True)
    # Untereinheiten: eigene Homepage auf ihrer Seite der Vereinswebseite verlinken
    website_on_site = models.BooleanField(
        "Homepage auf der Webseite verlinken", default=False, db_default=False
    )
    # Vorschaubild der Homepage: einmal von dort geholt (og:image) oder selbst hochgeladen
    website_image = models.ImageField(
        "Vorschaubild der Homepage", upload_to=homepage_image_path, blank=True
    )
    website_image_custom = models.BooleanField(
        "Vorschaubild selbst hochgeladen", default=False, db_default=False
    )
    # Für diese Adresse wurde zuletzt automatisch geholt (nur einmal je Adresse)
    website_image_for = models.CharField(max_length=200, blank=True, default="", db_default="")
    # Speicherbudget der Dokumentablage in GB (leer: DOCUMENT_BUDGET_GB, Standard 5);
    # erhöhen darf nur die Plattform (Gesamtaudit 01.11., GA-S04)
    document_budget_gb = models.PositiveSmallIntegerField(
        "Speicherbudget Dokumente (GB)", null=True, blank=True
    )

    # Vereinseinstellungen zu Abteilungen
    department_label = models.CharField(
        "Bezeichnung für Abteilungen (Einzahl)", max_length=50, default="Abteilung"
    )
    department_label_plural = models.CharField(
        "Bezeichnung für Abteilungen (Mehrzahl)", max_length=50, default="Abteilungen"
    )
    department_label_gender = models.CharField(
        "Bezeichnung für Abteilungen (Genus)",
        max_length=1,
        choices=[("f", "die (weiblich)"), ("m", "der (männlich)"), ("n", "das (sächlich)")],
        default="f",
    )
    department_label_genitive = models.CharField(
        "Bezeichnung für Abteilungen (Genitiv, falls abweichend)",
        max_length=50,
        blank=True,
        help_text="Leer: wird gebildet (des Zugs, des Kreises). Nur bei Ausnahmen eintragen.",
    )
    department_label_en = models.CharField(
        "Bezeichnung für Abteilungen englisch (Einzahl)",
        max_length=50,
        blank=True,
        default="",
        db_default="",
    )
    department_label_plural_en = models.CharField(
        "Bezeichnung für Abteilungen englisch (Mehrzahl)",
        max_length=50,
        blank=True,
        default="",
        db_default="",
    )
    allow_multiple_departments = models.BooleanField(
        "Mitglied darf mehreren Abteilungen angehören", default=True
    )
    # Vereine ohne Untereinheiten blenden den Menüpunkt aus (Ralf 15.11.2026)
    units_in_menu = models.BooleanField(
        "Menüpunkt für Untereinheiten zeigen", default=True, db_default=True
    )
    # Protokoll einer Versammlung: Leitung und Protokollführung bestätigen nicht mit demselben
    # Konto (Sicherheitsprüfung 26.11., B-M09). Vereine mit nur einem Konto schalten es ab.
    minutes_four_eyes = models.BooleanField(
        "Protokolle bestätigen zwei verschiedene Personen", default=True, db_default=True
    )
    # Anordnung des Menüs (konzepte/menue-frei-anordnen.md, organizations/menu_layout.py):
    # nur Abweichungen vom Standard, null = Standard. Untereinheiten übernehmen die des Vereins.
    menu_layout = models.JSONField("Anordnung des Menüs", null=True, blank=True)
    # Die letzten fünf vorigen Anordnungen für „Rückgängig“
    menu_layout_history = models.JSONField(
        "Frühere Anordnungen des Menüs", default=list, blank=True, db_default=[]
    )
    photo_approval_required = models.BooleanField(
        "Fotos von Mitgliedern erst nach Freigabe anzeigen", default=False
    )
    # Zugänge (Phase 2)
    member_portal_enabled = models.BooleanField(
        "Mitgliederbereich freigeschaltet",
        default=False,
        help_text="Mitglieder können sich anmelden und ihre Daten und Rechnungen sehen.",
    )
    card_wallet_enabled = models.BooleanField(
        "Mitgliedsausweis in Apple und Google Wallet anbieten",
        default=True,
        db_default=True,
        help_text="Nur wirksam, wenn der Betreiber Wallet eingerichtet hat.",
    )
    # Gesamtaudit 05.11. F-04: Plattform-Betreuung sieht im Postausgang sonst nur Kopfdaten
    outbox_platform_content = models.BooleanField(
        "Plattform-Betreuung darf Inhalte im Postausgang sehen",
        default=False,
        db_default=False,
        help_text="Text und Anhänge der Mails dieser Einheit, etwa zur Fehlersuche.",
    )
    contact_changes_need_approval = models.BooleanField(
        "Änderungen an Kontaktdaten erst nach Bestätigung durch den Verein", default=False
    )
    # Kündigung durch das Mitglied im Mitgliederbereich; Frist und Termin nach Satzung
    member_cancellation_enabled = models.BooleanField(
        "Mitglieder können im Mitgliederbereich kündigen", default=False, db_default=False
    )
    cancellation_notice_months = models.PositiveSmallIntegerField(
        "Kündigungsfrist in Monaten",
        default=3,
        db_default=3,
        validators=[MaxValueValidator(24)],
    )
    cancellation_period_end = models.CharField(
        "Kündigung wirksam",
        max_length=10,
        choices=CancellationEnd.choices,
        default=CancellationEnd.YEAR,
        db_default=CancellationEnd.YEAR,
    )
    department_access_enabled = models.BooleanField(
        "Zugang für Abteilungen freigeschaltet",
        default=False,
        help_text="Abteilungsrollen mit Rechten können sich anmelden.",
    )

    # Plattform-Schalter je Dachverband (Wirkung ab späteren Meilensteinen)
    federation_member_access = models.CharField(
        "Zugriff des Dachverbands auf Mitgliedsdaten",
        max_length=10,
        choices=MemberAccess.choices,
        default=MemberAccess.NONE,
    )
    federation_show_former_memberships = models.BooleanField(
        "Frühere Mitgliedschaften für Vereine sichtbar", default=False
    )

    # Jubiläen und Mitgliedsdauer (Meilenstein 4)
    jubilee_years = models.JSONField(
        "Jubiläumsstufen (Jahre)", default=default_jubilee_years, blank=True
    )
    # Jubiläen der Einheit selbst und ihrer Untereinheiten (aus dem Gründungsjahr)
    unit_jubilee_years = models.JSONField(
        "Jubiläumsstufen für Einheiten (Jahre)",
        default=default_unit_jubilee_years,
        blank=True,
    )
    federation_duration_rule = models.CharField(
        "Regel für die Mitgliedsdauer im Dachverband",
        max_length=20,
        choices=[
            ("all_reported", "alle gemeldeten Zeiten"),
            ("active_reported", "nur gemeldete aktive Zeiten"),
        ],
        default="all_reported",
    )
    date_precision = models.CharField(
        "Genauigkeit für Mitgliedschaften und Jubiläen",
        max_length=10,
        choices=DatePrecision.choices,
        default=DatePrecision.DAY,
        blank=True,
        help_text="Bei Untereinheiten leer: wie die übergeordnete Einheit.",
    )

    enabled_modules = models.JSONField("eingeschaltete Module", default=list, blank=True)
    # Von der Plattform freigegeben (Obergrenze für enabled_modules; konzepte/module-neustruktur.md
    # 5.3). Leer heißt für eine Fassung: wie enabled_modules (ältere Stände).
    released_modules = models.JSONField(
        "freigegebene Module", default=list, db_default=[], blank=True
    )
    # Dachverband: darf seinen Vereinen selbst Module freigeben (M6, Schalter der Plattform)
    modules_pass_down = models.BooleanField(
        "darf Module an seine Vereine weitergeben", default=False, db_default=False
    )
    # Untereinheiten: Module des Vereins, die der Verein für diese Einheit ausblendet (M5).
    # Leer heißt: alle Module des Vereins.
    unit_hidden_modules = models.JSONField(
        "für diese Untereinheit ausgeblendete Module", default=list, db_default=[], blank=True
    )
    shooting_facilities = models.JSONField(
        "verfügbare Schießinfrastruktur", default=None, null=True, blank=True
    )
    # Hilfe (konzepte/hilfe-funktion.md 3.6, 3.7): Ansprechpartner für Fragen zu HUBIplan
    # [{"name", "hint", "email"}] und Hinweise des Vereins zu Anleitungen {Schlüssel: Text}
    help_contacts = models.JSONField(
        "Ansprechpartner für Fragen zu HUBIplan", default=list, blank=True
    )
    help_notes = models.JSONField("Hinweise des Vereins zur Hilfe", default=dict, blank=True)
    # Vereinssprache (konzepte/englisch.md, Fachfrage F10): Sprache der Belege, Briefe,
    # Rechnungen und der Vereinswebseite. Vorerst immer Deutsch, noch nicht einstellbar.
    language = models.CharField(
        "Vereinssprache", max_length=5, choices=settings.LANGUAGES, default="de", db_default="de"
    )
    # Kasse: Kategorien den vier steuerlichen Bereichen zuordnen (entscheidet die Organisation)
    tax_areas_enabled = models.BooleanField("steuerliche Bereiche in der Kasse", default=False)
    # Kasse: Buchungen bis einschließlich diesem Tag sind festgeschrieben (GoBD); nur vorwärts
    finance_locked_until = models.DateField("Kasse festgeschrieben bis", null=True, blank=True)
    # Kasse: Abschluss aufheben nur zu zweit (Kasse beantragt, Vorsitz bestätigt; Gesamtaudit
    # 11.11., Fachfrage 5), für Vereine mit Prüfpflicht
    finance_reopen_four_eyes = models.BooleanField(
        "Abschluss aufheben nur zu zweit", default=False, db_default=False
    )
    # Kasse: Zählprotokoll (Kassensturz) und Kassenbericht für Feste (offene Ladenkasse)
    cash_counts_enabled = models.BooleanField(
        "Zählprotokoll und Kassenbericht für Feste", default=False
    )
    # Kasse: Umsätze direkt bei der Bank abrufen (FinTS); zusätzlich muss der Betreiber die
    # Bankanbindung auf dem Server eingeschaltet haben (docs/bankanbindung.md)
    bank_access_enabled = models.BooleanField("Bankanbindung", default=False, db_default=False)
    # Früher: Geschäftspartner oben im Hauptmenü. Nicht mehr verwendet; die Spalte bleibt eine
    # Fassung lang für den Rückweg und wird im nächsten Release entfernt (docs/releases.md).
    partners_in_menu = models.BooleanField(
        "Geschäftspartner im Hauptmenü", default=False, db_default=False
    )
    # Kasse: Rücklagen nach § 62 AO führen (Finanzamt-Prüfung C4)
    reserves_enabled = models.BooleanField("Rücklagen führen", default=False, db_default=False)
    # Kasse: DATEV-Export für die Steuerberatung (Buchungsstapel, zuschaltbar)
    datev_enabled = models.BooleanField("DATEV-Export", default=False)
    datev_consultant = models.CharField("DATEV Beraternummer", max_length=7, blank=True)
    datev_client = models.CharField("DATEV Mandantennummer", max_length=5, blank=True)
    datev_account_length = models.PositiveSmallIntegerField("DATEV Sachkontenlänge", default=4)
    datev_chart = models.CharField("Kontenrahmen", max_length=20, blank=True)
    # Untereinheiten: eigener Arbeitsbereich mit eigener Kasse und eigenen Rollen.
    # Die Mitglieder bleiben in der Einheit mit den Mitgliedschaften.
    own_workspace = models.BooleanField(
        "eigener Arbeitsbereich",
        default=False,
        help_text="Eigene Kasse und eigene Rollen mit Zugängen.",
    )
    # Untereinheiten: steuerlich selbständig (eigener Bescheid). Sonst zählen ihre Zahlen
    # beim Verein mit (Freigrenze § 64 Abs. 3 und 4 AO, Kleinunternehmergrenze).
    tax_independent = models.BooleanField("steuerlich selbständig", default=False, db_default=False)
    # Pauschalen an Vorstandsmitglieder nur, wenn die Satzung es erlaubt (§ 27 Abs. 3 BGB)
    board_pay_allowed = models.BooleanField(
        "Satzung erlaubt Vergütung des Vorstands", default=False, db_default=False
    )
    # Umsatzsteuer in der Kasse (Konzept vereinskasse-steuern, S2)
    vat_period = models.CharField(
        "Voranmeldungszeitraum",
        max_length=8,
        choices=[("month", "monatlich"), ("quarter", "vierteljährlich"), ("year", "jährlich")],
        default="quarter",
        db_default="quarter",
    )
    vat_flat_rate = models.BooleanField(
        "Vorsteuer pauschal nach § 23a UStG", default=False, db_default=False
    )
    # Untereinheiten: Rolleninhaber bekommen eigene Zugänge mit Rechten. Aus: die
    # Einheit darüber verwaltet sie, ihre Rollen sind reine Ämter.
    self_managed = models.BooleanField(
        "verwaltet sich selbst",
        default=False,
        help_text="Rolleninhaber der Untereinheit bekommen Zugänge mit Rechten.",
    )
    # Oberste Einheit mit Untereinheiten (Dachverband): führt auch selbst
    # Mitglieder, z. B. passive Mitglieder ohne Mitgliedschaft darunter.
    direct_members = models.BooleanField(
        "führt eigene Mitglieder",
        default=False,
        help_text="Mitglieder direkt in dieser Einheit, ohne Mitgliedschaft darunter.",
    )
    # Termine: Weitergabe der eigenen, nicht internen Termine an die Einheiten
    # darüber bzw. darunter. Einzelne Termine können abweichen (Event.share_*).
    events_share_up = models.BooleanField(
        "eigene Termine nach oben freigeben",
        default=False,
        help_text="Die eigenen Termine erscheinen im Kalender der übergeordneten Einheit.",
    )
    events_share_down = models.BooleanField(
        "eigene Termine nach unten freigeben",
        default=True,
        help_text="Die eigenen Termine erscheinen bei den Untereinheiten und ihren Mitgliedern.",
    )
    # Untereinheiten: wer ihr (oder einer Einheit darunter) angehört, zahlt keinen
    # Vereinsbeitrag. Der Verbandsbeitrag an den Dachverband bleibt.
    fee_exempt = models.BooleanField(
        "Mitglieder beitragsfrei",
        default=False,
        help_text="Mitglieder dieser Einheit und der Einheiten darunter zahlen keinen Beitrag.",
    )
    is_active = models.BooleanField("aktiv", default=True)
    # Mit einer Einheit darüber stillgelegt: wird mit ihr wieder aktiv (FQ-14)
    inactive_by_parent = models.BooleanField(default=False, editable=False)
    # Platzhalter einer gekoppelten Einheit auf einer anderen Instanz (App peering):
    # ohne Mitglieder, Kasse und Zugänge, nur mit übermittelten Daten
    is_remote = models.BooleanField("auf anderer Instanz", default=False, editable=False)
    # Löschung vorgemerkt (Gesamtaudit 10.11., F02): stillgelegt, Daten bleiben bis zum
    # endgültigen Löschen nach den Aufbewahrungsfristen (organizations/deletion.py)
    erase_requested_at = models.DateTimeField(
        "Löschung vorgemerkt am", null=True, blank=True, editable=False
    )
    erase_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
        verbose_name="Löschung vorgemerkt von",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organisation"
        verbose_name_plural = "Organisationen"
        ordering = ["type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["type"],
                condition=models.Q(type="platform"),
                name="nur_eine_plattform",
            ),
            # Dazu kommt der Index „untereinheit_name_je_einheit“ (Migration 0014):
            # Namen von Untereinheiten sind je übergeordneter Einheit eindeutig.
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self._sync_portal(kwargs)
        loaded = getattr(self, "_loaded_active", None)
        active_changed = not self._state.adding and loaded is not None and loaded != self.is_active
        if active_changed and self.is_active:
            self.inactive_by_parent = False
            fields = kwargs.get("update_fields")
            if fields is not None and "is_active" in fields:
                kwargs["update_fields"] = {*fields, "inactive_by_parent"}
        self._save_with_labels(*args, **kwargs)
        self._loaded_active = self.is_active
        self._loaded_portal = (self.member_portal_enabled, "portal" in (self.enabled_modules or []))
        if active_changed and self.type in (self.Type.FEDERATION, self.Type.CLUB, self.Type.UNIT):
            from ..activity import cascade_active

            cascade_active(self)

    def _sync_portal(self, kwargs) -> None:
        """Modul „Mitgliederbereich“ und Schalter ``member_portal_enabled`` gleich halten.

        Der Schalter bleibt eine Fassung lang für ältere Stände erhalten. Wer zuletzt
        geändert wurde, gilt; bei neuen Einheiten reicht eines von beiden.
        """
        if self.type != self.Type.CLUB:
            return
        modules = set(self.enabled_modules or [])
        on = "portal" in modules
        loaded = getattr(self, "_loaded_portal", None)
        if loaded is None:
            wanted = on or self.member_portal_enabled
        elif self.member_portal_enabled != loaded[0]:
            wanted = self.member_portal_enabled
        elif on != loaded[1]:
            wanted = on
        else:
            wanted = self.member_portal_enabled
        if wanted == on and wanted == self.member_portal_enabled:
            return
        self.member_portal_enabled = wanted
        self.enabled_modules = sorted(modules | {"portal"} if wanted else modules - {"portal"})
        fields = kwargs.get("update_fields")
        if fields is not None:
            kwargs["update_fields"] = {*fields, "member_portal_enabled", "enabled_modules"}

    def _save_with_labels(self, *args, **kwargs):
        if self._state.adding and self.type in DEFAULT_CHILD_LABELS:
            if self.department_label == "Abteilung":
                (
                    self.department_label,
                    self.department_label_plural,
                    self.department_label_gender,
                    self.department_label_genitive,
                ) = DEFAULT_CHILD_LABELS[self.type]
        if not self.label and self.type in DEFAULT_LABELS:
            (self.label, self.label_plural, self.label_gender, self.label_genitive) = (
                DEFAULT_LABELS[self.type]
            )
        super().save(*args, **kwargs)
        if self.type in (self.Type.FEDERATION, self.Type.CLUB, self.Type.UNIT):
            # Solange Untereinheiten keine eigene Bezeichnung pflegen, folgt sie der
            # Vorgabe der direkt übergeordneten Einheit („Bezeichnung der Untereinheiten“).
            Organization.objects.filter(parent=self, type=self.Type.UNIT).update(
                label=self.department_label,
                label_plural=self.department_label_plural,
                label_gender=self.department_label_gender,
                label_genitive=self.department_label_genitive,
                label_en=self.department_label_en,
                label_plural_en=self.department_label_plural_en,
            )

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_active = instance.__dict__.get("is_active")
        if "member_portal_enabled" in instance.__dict__ and "enabled_modules" in instance.__dict__:
            instance._loaded_portal = (
                instance.member_portal_enabled,
                "portal" in (instance.enabled_modules or []),
            )
        return instance

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.type == self.Type.PLATFORM:
            if self.parent_id:
                errors["parent"] = gettext("Die Plattform hat keine übergeordnete Organisation.")
        elif self.type == self.Type.FEDERATION:
            if self.parent and self.parent.type != self.Type.PLATFORM:
                errors["parent"] = gettext("Ein Dachverband hängt direkt unter der Plattform.")
        elif self.type == self.Type.CLUB:
            if self.parent and self.parent.type not in (self.Type.PLATFORM, self.Type.FEDERATION):
                errors["parent"] = gettext(
                    "Ein Verein gehört zur Plattform oder zu einem Dachverband."
                )
        elif self.type == self.Type.UNIT:
            if self.parent_id is None or self.organization_id is None:
                errors["parent"] = gettext("Eine Untereinheit braucht eine übergeordnete Einheit.")
            else:
                error = self.parent_error()
                if error:
                    errors["parent"] = error
        if self.type in (self.Type.FEDERATION, self.Type.CLUB):
            for field in ("founding_year", "street", "postal_code", "city"):
                if not getattr(self, field):
                    errors[field] = gettext("Pflichtfeld.")
        if self.contact_role_id and (
            self.contact_role.organization_id != self.pk or self.contact_role.department_id
        ):
            errors["contact_role"] = gettext("Die Rolle muss zu dieser Organisation gehören.")
        if self.contact_source == self.ContactSource.ROLE and not self.contact_role_id:
            errors["contact_role"] = gettext("Bitte eine Rolle wählen.")
        if self.erase_requested_at and self.is_active:
            errors["is_active"] = gettext(
                "Die Löschung ist vorgemerkt. Bitte erst die Vormerkung zurücknehmen."
            )
        if errors:
            raise ValidationError(errors)

    def parent_error(self) -> str | None:
        """Prüft die übergeordnete Einheit einer Untereinheit (Datenbereich, Kreis, Tiefe)."""
        from ..tree import MAX_DEPTH

        if self.parent_id == self.organization_id:
            return None
        parent = Organization.objects.filter(pk=self.parent_id).first()
        if (
            parent is None
            or parent.type != self.Type.UNIT
            or parent.organization_id != self.organization_id
        ):
            return "Die übergeordnete Einheit muss zum selben Bereich gehören."
        depth, node, seen = 1, parent, set()
        while node is not None and node.type == self.Type.UNIT:
            if (self.pk and node.pk == self.pk) or node.pk in seen:
                # seen: auch ein schon vorhandener Kreis führt nicht zur Endlosschleife
                return "Eine Einheit kann nicht unter sich selbst oder ihren Untereinheiten hängen."
            seen.add(node.pk)
            depth += 1
            node = node.parent
        if self.pk:
            # Beim Umhängen wandern die Untereinheiten mit
            from ..tree import UnitTree

            tree = UnitTree.of(self.organization_id)
            depth += max((tree.depth(i) for i in tree.subtree(self.pk)), default=0) - (
                tree.depth(self.pk)
            )
        if depth > MAX_DEPTH:
            return f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich."
        return None

    @property
    def kind_label(self) -> str:
        """Bezeichnung der Einheit (z. B. „Verein“), sonst die technische Art."""
        return self.label or self.get_type_display()

    @property
    def effective_date_precision(self) -> str:
        """Genauigkeit; leer bei Untereinheiten heißt: wie die übergeordnete Einheit."""
        node = self
        while node is not None:
            if node.date_precision:
                return node.date_precision
            node = node.parent
        return DatePrecision.DAY

    @property
    def tax_areas_on(self) -> bool:
        """Steuerliche Bereiche in der Kasse: Schalter und Modul „Steuern & Gemeinnützigkeit“."""
        from access.modules import module_on

        return bool(self.tax_areas_enabled) and module_on(self, "tax")

    @property
    def reserves_on(self) -> bool:
        """Rücklagen nach § 62 AO: Schalter und Modul „Steuern & Gemeinnützigkeit“."""
        from access.modules import module_on

        return bool(self.reserves_enabled) and module_on(self, "tax")

    @property
    def keeps_members(self) -> bool:
        """Führt diese Einheit selbst Mitgliedschaften?"""
        if self.type == self.Type.CLUB:
            return True
        return self.type == self.Type.FEDERATION and self.direct_members

    @property
    def federation(self) -> Organization | None:
        if self.type == self.Type.CLUB and self.parent and self.parent.type == self.Type.FEDERATION:
            return self.parent
        return None

    def ancestors(self) -> list[Organization]:
        """Kette nach oben: [self, parent, …, Plattform]."""
        chain, node = [], self
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain

    @classmethod
    def platform(cls) -> Organization:
        org, _ = cls.objects.get_or_create(type=cls.Type.PLATFORM, defaults={"name": "HUBIplan"})
        return org


# Eine verkürzte Löschfrist gilt erst nach so vielen Tagen (Zeit zum Bemerken und Sichern)
DELETION_SHORTEN_GRACE_DAYS = 30


class DepartmentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=Organization.Type.UNIT)


class Department(Organization):
    """Untereinheit (früher „Abteilung“): eine Einheit ohne eigenen Datenbereich.

    Sie liegt in derselben Tabelle wie alle Einheiten. ``organization`` ist die
    Einheit, in deren Datenbereich ihre Daten liegen, ``parent`` die direkt
    übergeordnete Einheit.
    """

    objects = DepartmentManager()

    # Im Änderungsprotokoll nur die Felder, die Untereinheiten pflegen
    audit_fields = frozenset(
        {
            "name",
            "short_name",
            "founding_year",
            "website",
            "website_on_site",
            "website_image",
            "sort_order",
            "date_precision",
            "is_active",
            "fee_exempt",
            "fiscal_start_month",
            "fiscal_start_day",
            "primary_color",
            "accent_color",
            "primary_color_name",
            "accent_color_name",
            "extra_colors",
            "primary_color_use",
            "accent_color_use",
            "gradients",
            "palette_roles",
            "palette_roles_in_app",
            "logo",
            "logo_dark",
            "own_workspace",
            "self_managed",
            "tax_independent",
            "parent",
        }
    )

    class Meta:
        proxy = True
        verbose_name = "Abteilung"
        verbose_name_plural = "Abteilungen"
        ordering = ["sort_order", "name"]

    def __init__(self, *args, **kwargs):
        # Neue Untereinheiten erben die Genauigkeit, solange keine gesetzt ist
        if not args and "date_precision" not in kwargs:
            kwargs["date_precision"] = ""
        # Termine von Untereinheiten erscheinen wie bisher auch darüber
        if not args and "events_share_up" not in kwargs:
            kwargs["events_share_up"] = True
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.type = Organization.Type.UNIT
        if self.own_workspace:
            # Ein Arbeitsbereich hat Zugänge, also verwaltet sich die Einheit selbst
            self.self_managed = True
        if self.own_workspace and not WORKSPACE_MODULES <= set(self.enabled_modules or []):
            # Arbeitsbereich: Kasse und Rechnungen
            self.enabled_modules = sorted({*(self.enabled_modules or []), *WORKSPACE_MODULES})
        if self.parent_id is None:
            self.parent_id = self.organization_id
        from core.reorder import append_if_new

        append_if_new(self, "sort_order", Organization.objects.filter(parent_id=self.parent_id))
        if self._state.adding and self.parent_id and not self.label:
            # Bezeichnung nach der Vorgabe der direkt übergeordneten Einheit
            above = Organization.objects.get(pk=self.parent_id)
            self.label = above.department_label
            self.label_plural = above.department_label_plural
            self.label_gender = above.department_label_gender
            self.label_genitive = above.department_label_genitive
        super().save(*args, **kwargs)


class DepartmentRoleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(department__isnull=False)


class DepartmentRole(Role):
    """Rolle einer Untereinheit (z. B. Zugführer, Kassierer): dieselbe Rolle wie
    ``access.Role``, nur auf die Rollen von Untereinheiten beschränkt.

    Mit Rechten aus dem Katalog der Untereinheiten (``access.catalog.DEPARTMENT_CODES``)
    und freigeschaltetem Zugang dürfen sich Inhaber anmelden.
    """

    objects = DepartmentRoleManager()

    class Meta:
        proxy = True
        verbose_name = "Rolle der Untereinheit"
        verbose_name_plural = "Rollen der Untereinheiten"
        ordering = ["position", "name"]
        default_manager_name = "objects"
