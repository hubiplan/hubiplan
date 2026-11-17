"""Briefbogen je Einheit und die gemerkten Wahlen der Vorstände.

Erzeugte Word-Dateien werden nicht gespeichert. Je Person und Einheit merkt sich
HUBIplan nur die Wahl im Dialog und Prüfwerte der verwendeten Daten, damit es
später „Vorlage veraltet“ melden kann.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from organizations.models import Organization, validate_logo


def letterhead_logo_path(instance, filename: str) -> str:
    """Eigenes Logo des Briefbogens (Issue #488); immer PNG, nie eine Seitenendung."""
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"logos/briefbogen/{instance.organization_id or 'neu'}-{stamp}.png"


class Letterhead(models.Model):
    class Mode(models.TextChoices):
        OWN = "own", gettext_lazy("eigener Briefbogen")
        INHERIT = "inherit", gettext_lazy("Briefbogen der übergeordneten Einheit")

    class Form(models.TextChoices):
        A = "a", gettext_lazy("DIN 5008 Form A (Anschriftfeld 27 mm von oben)")
        B = "b", gettext_lazy("DIN 5008 Form B (Anschriftfeld 45 mm von oben)")

    class LogoPosition(models.TextChoices):
        RIGHT = "right", gettext_lazy("rechts")
        LEFT = "left", gettext_lazy("links")
        NONE = "none", gettext_lazy("ohne Logo/Wappen")

    class Font(models.TextChoices):
        ARIAL = "Arial", gettext_lazy("Arial")
        CALIBRI = "Calibri", gettext_lazy("Calibri")
        CAMBRIA = "Cambria", gettext_lazy("Cambria")
        GEORGIA = "Georgia", gettext_lazy("Georgia")
        TIMES = "Times New Roman", gettext_lazy("Times New Roman")
        VERDANA = "Verdana", gettext_lazy("Verdana")
        # Schriften der Webseite; im PDF eingebettet, in Word mit Ersatzschrift (Issue #470)
        SOURCE_SANS = "Source Sans 3", gettext_lazy("Source Sans 3")
        CRIMSON = "Crimson Pro", gettext_lazy("Crimson Pro")
        ATKINSON = "Atkinson Hyperlegible", gettext_lazy("Atkinson Hyperlegible")
        OPEN_SANS = "Open Sans", gettext_lazy("Open Sans")
        ROBOTO = "Roboto", gettext_lazy("Roboto")
        OSWALD = "Oswald", gettext_lazy("Oswald")
        FRAKTUR = "UnifrakturMaguntia", gettext_lazy("UnifrakturMaguntia (Fraktur)")

    class OfficeFont(models.TextChoices):
        """Ersatzschrift in Word, wenn die gewählte Schrift dort nicht installiert ist."""

        ARIAL = "Arial", gettext_lazy("Arial")
        CALIBRI = "Calibri", gettext_lazy("Calibri")
        CAMBRIA = "Cambria", gettext_lazy("Cambria")
        GEORGIA = "Georgia", gettext_lazy("Georgia")
        TIMES = "Times New Roman", gettext_lazy("Times New Roman")
        VERDANA = "Verdana", gettext_lazy("Verdana")

    class LogoSize(models.TextChoices):
        SMALL = "small", gettext_lazy("klein")
        MEDIUM = "medium", gettext_lazy("mittel")
        LARGE = "large", gettext_lazy("groß")

    class Slot(models.TextChoices):
        """Platz in der Palette der Einheit (0 Hauptfarbe, 1 Zweitfarbe, 2–5 weitere)."""

        P0 = "0", gettext_lazy("Hauptfarbe")
        P1 = "1", gettext_lazy("Zweitfarbe")
        P2 = "2", gettext_lazy("Farbe 3")
        P3 = "3", gettext_lazy("Farbe 4")
        P4 = "4", gettext_lazy("Farbe 5")
        P5 = "5", gettext_lazy("Farbe 6")

    class TitleColor(models.TextChoices):
        BLACK = "black", gettext_lazy("Schwarz")
        PRIMARY = "primary", gettext_lazy("Hauptfarbe")

    class Stripe(models.TextChoices):
        GREY = "grey", gettext_lazy("hellgrau")
        NONE = "none", gettext_lazy("keine Streifen")
        P0 = "0", gettext_lazy("Hauptfarbe, hell")
        P1 = "1", gettext_lazy("Zweitfarbe, hell")
        P2 = "2", gettext_lazy("Farbe 3, hell")
        P3 = "3", gettext_lazy("Farbe 4, hell")
        P4 = "4", gettext_lazy("Farbe 5, hell")
        P5 = "5", gettext_lazy("Farbe 6, hell")

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="letterhead"
    )
    mode = models.CharField("Briefbogen", max_length=10, choices=Mode.choices)
    form = models.CharField("Form", max_length=1, choices=Form.choices, default=Form.B)
    logo_position = models.CharField(
        "Logo/Wappen", max_length=10, choices=LogoPosition.choices, default=LogoPosition.RIGHT
    )
    tagline = models.CharField(
        "Zusatzzeile im Kopf",
        max_length=150,
        blank=True,
        help_text="z. B. „gegründet 1920“; leer: keine Zusatzzeile.",
    )
    font = models.CharField("Schriftart", max_length=40, choices=Font.choices, default=Font.ARIAL)
    # Gestaltung (Issue #470); die Grundwerte entsprechen dem bisherigen festen Aussehen
    heading_font = models.CharField(
        "Schrift für Name und Überschriften",
        max_length=40,
        choices=[("", gettext_lazy("wie der Text")), *Font.choices],
        default="",
        db_default="",
        blank=True,
    )
    font_fallback = models.CharField(
        "Ersatzschrift in Word (Text)",
        max_length=40,
        choices=OfficeFont.choices,
        default=OfficeFont.ARIAL,
        db_default=OfficeFont.ARIAL,
    )
    heading_font_fallback = models.CharField(
        "Ersatzschrift in Word (Überschriften)",
        max_length=40,
        choices=OfficeFont.choices,
        default=OfficeFont.GEORGIA,
        db_default=OfficeFont.GEORGIA,
    )
    show_name = models.BooleanField("Name neben dem Logo zeigen", default=True, db_default=True)
    # Eigenes Logo nur für den Briefbogen (Issue #488); leer: Logo aus dem Erscheinungsbild
    logo = models.ImageField(
        "Logo für den Briefbogen",
        upload_to=letterhead_logo_path,
        blank=True,
        default="",
        db_default="",
        validators=[validate_logo],
    )
    # Eigener Name im Briefkopf mit selbst gewähltem Umbruch (Issue #487); leer: Name der Einheit
    head_name = models.CharField(
        "Name im Briefkopf",
        max_length=200,
        blank=True,
        default="",
        db_default="",
        help_text="Höchstens zwei Zeilen; leer: der Name der Einheit.",
    )
    head_name_small = models.BooleanField("Zweite Zeile kleiner", default=False, db_default=False)
    logo_size = models.CharField(
        "Größe von Logo/Wappen",
        max_length=10,
        choices=LogoSize.choices,
        default=LogoSize.MEDIUM,
        db_default=LogoSize.MEDIUM,
    )
    line_color = models.CharField(
        "Linienfarbe", max_length=1, choices=Slot.choices, default=Slot.P1, db_default=Slot.P1
    )
    head_line = models.BooleanField("Linie unter dem Kopf", default=True, db_default=True)
    footer_line = models.BooleanField("Linie über der Fußzeile", default=True, db_default=True)
    title_color = models.CharField(
        "Farbe von Titel und Betreff",
        max_length=10,
        choices=TitleColor.choices,
        default=TitleColor.BLACK,
        db_default=TitleColor.BLACK,
    )
    table_line_color = models.CharField(
        "Linien in Tabellen",
        max_length=1,
        choices=Slot.choices,
        default=Slot.P0,
        db_default=Slot.P0,
    )
    table_stripe = models.CharField(
        "Streifen in Tabellen",
        max_length=4,
        choices=Stripe.choices,
        default=Stripe.GREY,
        db_default=Stripe.GREY,
    )
    salutation = models.CharField(
        "Anrede", max_length=100, default="Sehr geehrte Damen und Herren,"
    )
    closing = models.CharField("Grußformel", max_length=100, default="Mit freundlichen Grüßen")
    show_bank = models.BooleanField("Bankverbindung zeigen", default=True)
    account = models.ForeignKey(
        "finance.Account",
        verbose_name="Bankkonto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Leer: erstes aktives Bankkonto mit IBAN.",
    )
    show_email = models.BooleanField("E-Mail der Einheit zeigen", default=True)
    show_phone = models.BooleanField("Telefon der Einheit zeigen", default=True)
    show_website = models.BooleanField("Webseite zeigen", default=True)
    show_board = models.BooleanField("Vorstand zeigen", default=True)
    show_register = models.BooleanField("Registerangaben und USt-IdNr. zeigen", default=True)
    show_social = models.BooleanField("Social-Media-Kanäle zeigen", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Briefbogen"
        verbose_name_plural = "Briefbögen"

    def __str__(self) -> str:
        return f"Briefbogen {self.organization}"

    @staticmethod
    def default_mode(org: Organization) -> str:
        if org.type == Organization.Type.UNIT:
            return Letterhead.Mode.INHERIT
        return Letterhead.Mode.OWN


class LetterheadChoice(models.Model):
    """Was eine Person zuletzt für eine Einheit gewählt hat (ohne Inhalte)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="letterhead_choices"
    )
    unit = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    # Absenderkontext: „org:<id>“ (Rolle der Einheit) oder „dept:<id>“ (Rolle der Untereinheit)
    context = models.CharField(max_length=30)
    function = models.CharField(max_length=30, blank=True)
    function_text = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=30, blank=True)
    contacts = models.JSONField(default=list, blank=True)
    with_logo = models.BooleanField(default=True)
    file_format = models.CharField(max_length=4, default="dotx")
    # Prüfwerte je Abschnitt (HMAC), nie die Werte selbst
    checksums = models.JSONField(default=dict, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    hint_dismissed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wahl für die Briefvorlage"
        verbose_name_plural = "Wahlen für die Briefvorlage"
        constraints = [
            models.UniqueConstraint(fields=["user", "unit"], name="briefvorlage_wahl_je_einheit")
        ]

    def __str__(self) -> str:
        return f"{self.user} – {self.unit}"


class LetterheadProposal(models.Model):
    """Vorschlag für die Texte eines Briefbogens, abgelegt über die KI-Schnittstelle.

    Gesamtaudit 15.11., MCP-01, Fachfrage FF-12 (a): Freitexte des Briefbogens stehen auf allen
    neuen Rechnungen, Mahnungen und Spendenquittungen. Ein Assistent ändert sie deshalb nie
    selbst; er legt einen Vorschlag ab, den eine Person in HUBIplan übernimmt oder verwirft.
    Der Vorschlag verfällt nach ``PROPOSAL_DAYS`` und mit der Verbindung des Assistenten."""

    PROPOSAL_DAYS = 30

    # Einheit, in deren Bereich der Vorschlag liegt (Zeilenschutz)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    # Briefbogen dieser Einheit oder Untereinheit
    target = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    # Feld des Briefbogens → vorgeschlagener Text
    texts = models.JSONField(default=dict)
    grant = models.ForeignKey(
        "mcpserver.McpGrant", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    via = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = gettext_lazy("Vorschlag für den Briefbogen")

    def __str__(self) -> str:
        return f"Vorschlag {self.pk} ({', '.join(sorted(self.texts or {}))})"
