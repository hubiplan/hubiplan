"""Anmeldung an der Nextcloud (und ähnlichen Diensten) mit dem HUBIplan-Konto.

HUBIplan ist dafür Anbieter nach OpenID Connect (siehe ``provider``). Jede Einheit trägt
ihre Nextcloud als ``Client`` ein und legt fest, wer sich anmelden darf und welche
Gruppen mitgehen. Codes und Zugriffsschlüssel liegen nur kurz im Cache, nie in der
Datenbank.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_client_id() -> str:
    return "hp-" + secrets.token_urlsafe(18)


def new_salt() -> str:
    return secrets.token_urlsafe(32)


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Konten der Nextcloud-Verwaltung: nie über HUBIplan zuordnen (Gesamtaudit 15.11., AUTH-07;
# docs/nextcloud.md). Dazu kommt das Dienstkonto des jeweiligen Dienstes.
NEVER_USERNAMES = frozenset({"admin", "root", "administrator"})


def parse_usernames(text: str, blocked=frozenset()) -> list[tuple[str, str, str]]:
    """Zeilen „E-Mail = Benutzername“ → (E-Mail, Name, Fehler). Leer und # wird übersprungen.

    Fehler „blocked“: Verwaltungs- oder Dienstkonto, das nie zugeordnet wird."""
    out: list[tuple[str, str, str]] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = "=" if "=" in line else ":"
        email, _, name = (part.strip() for part in line.partition(sep))
        email, name = email.lower(), name.lower()
        if not EMAIL_RE.match(email):
            out.append((email, name, "email"))
        elif not USERNAME_RE.match(name):
            out.append((email, name, "name"))
        elif name in NEVER_USERNAMES or name in blocked:
            out.append((email, name, "blocked"))
        else:
            out.append((email, name, ""))
    return out


# Gruppennamen in der Nextcloud dürfen höchstens 64 Zeichen haben
GROUP_MAX = 64


def clean_groups(value) -> list[str]:
    """Gruppen aus Liste oder Text „A, B“: Leerraum gekürzt, leere und doppelte entfernt."""
    items = value.split(",") if isinstance(value, str) else list(value or [])
    groups = [" ".join(str(g).split()) for g in items]
    return list(dict.fromkeys(g for g in groups if g))


class Client(models.Model):
    class Audience(models.TextChoices):
        BOARD = "board", gettext_lazy("Vorstand und Rollen")
        ROLES = "roles", gettext_lazy("nur Rollen dieser Einheit")
        MEMBERS = "members", gettext_lazy("zusätzlich Mitglieder mit Zugang")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="oidc_clients"
    )
    name = models.CharField("Name", max_length=100, default="Nextcloud")
    # Adresse der Nextcloud, z. B. https://cloud.example.org (ohne /index.php)
    base_url = models.URLField("Adresse der Nextcloud", max_length=300)
    client_id = models.CharField("Client-ID", max_length=64, unique=True, default=new_client_id)
    # Nur die Prüfsumme; das Geheimnis sieht man einmal beim Anlegen bzw. Erneuern
    secret_hash = models.CharField(max_length=64)
    # Macht die Kennung (sub) je Dienst verschieden: Zwei Dienste können ihre Nutzer
    # nicht über die Kennung zusammenführen.
    subject_salt = models.CharField(max_length=64, default=new_salt)
    audience = models.CharField(
        "Wer darf sich anmelden", max_length=10, choices=Audience.choices, default=Audience.BOARD
    )
    require_mfa = models.BooleanField("nur mit Zwei-Faktor-Anmeldung", default=False)
    # Fachfrage FQ26: Anmeldung nur mit PKCE (S256); user_oidc schickt es von selbst mit
    require_pkce = models.BooleanField("nur mit PKCE (S256)", default=True)
    groups_board = models.BooleanField("Gruppe „Vorstand“", default=True)
    groups_roles = models.BooleanField("je Rolle eine Gruppe", default=True)
    groups_units = models.BooleanField("je Untereinheit eine Gruppe", default=True)
    groups_members = models.BooleanField("Gruppe „Mitglieder“", default=True)
    # Bisherige Benutzernamen in der Nextcloud, je Zeile „E-Mail = Benutzername“. Wer hier
    # steht, wird bei der ersten Anmeldung mit seinem vorhandenen Nextcloud-Konto verbunden
    # (Angabe preferred_username). Bewusst nur von Hand gepflegt: Aus Namen abgeleitet könnte
    # sich jemand durch eine Namensänderung ein fremdes Konto holen.
    usernames = models.TextField("bisherige Benutzernamen", blank=True, default="")
    # Gruppen für Rollen: Rollen-ID → Gruppen, z. B. „1. Kassierer“ und „2. Kassierer“ →
    # „Kassierer“. An der ID statt am Namen, damit Umbenennen nichts ändert. Rollen ohne
    # Eintrag schicken ihren Namen, wenn ``groups_roles`` an ist.
    role_groups = models.JSONField("Gruppen für Rollen", default=dict, blank=True)
    # Konten in der Nextcloud automatisch deaktivieren, wenn der Zugang endet (siehe accounts)
    manage_accounts = models.BooleanField("Konten automatisch deaktivieren", default=False)
    # Dienstkonto in der Nextcloud (Gruppen-Admin der Gruppe ``account_group``) mit App-Passwort
    service_user = models.CharField("Dienstkonto", max_length=64, blank=True, default="")
    # verschlüsselt (accounts.mfa.encrypt), nie in Antworten oder im Protokoll
    service_password = models.TextField(blank=True, default="")
    # Gruppe, die bei jeder Anmeldung mitgeht; das Dienstkonto verwaltet nur ihre Mitglieder
    account_group = models.CharField(
        "Gruppe der Konten über HUBIplan", max_length=64, blank=True, default=""
    )
    # Termine per CalDAV in Kalender des Dienstkontos schreiben und für Gruppen freigeben
    # (nur lesend; siehe ``nc_calendars`` und docs/nextcloud.md)
    calendar_members = models.BooleanField(
        "Termine für Mitglieder in die Nextcloud", default=False, db_default=False
    )
    calendar_members_group = models.CharField(
        "Gruppe für die Termine",
        max_length=64,
        blank=True,
        default="Mitglieder",
        db_default="Mitglieder",
    )
    calendar_board = models.BooleanField(
        "Termine „nur Vorstand“ in die Nextcloud", default=False, db_default=False
    )
    calendar_board_group = models.CharField(
        "Gruppe für die Vorstandstermine",
        max_length=64,
        blank=True,
        default="Vorstand",
        db_default="Vorstand",
    )
    calendar_error = models.CharField(max_length=500, blank=True, default="", db_default="")
    calendar_synced_at = models.DateTimeField(null=True, blank=True)
    # Gruppen auch zwischen den Anmeldungen abgleichen (siehe ``nc_groups``): ``user_oidc``
    # setzt Gruppen nur beim Anmelden, Sync-Apps melden sich nie neu an. HUBIplan ändert nur die
    # hier genannten Gruppen (und die Kontengruppe); das Dienstkonto muss ihr Gruppen-Admin sein.
    sync_groups = models.BooleanField("Gruppen laufend abgleichen", default=False, db_default=False)
    sync_groups_list = models.CharField(
        "Gruppen, die HUBIplan abgleicht",
        max_length=500,
        blank=True,
        default="",
        db_default="",
    )
    groups_error = models.CharField(max_length=500, blank=True, default="", db_default="")
    groups_synced_at = models.DateTimeField(null=True, blank=True)
    # Dateien „In Nextcloud ablegen“ (siehe ``nc_files``): Ordner im Dienstkonto, je Ziel nur
    # lesend an eine Gruppe freigegeben; HUBIplan löscht abgelegte Dateien nach der Frist je Art
    files_enabled = models.BooleanField("In Nextcloud ablegen", default=False, db_default=False)
    files_root = models.CharField(
        "Ordner im Dienstkonto",
        max_length=100,
        blank=True,
        default="HUBIplan",
        db_default="HUBIplan",
    )
    files_board_group = models.CharField(
        "Gruppe für „Vorstand“",
        max_length=64,
        blank=True,
        default="Vorstand",
        db_default="Vorstand",
    )
    files_finance_group = models.CharField(
        "Gruppe für „Kasse“", max_length=64, blank=True, default="Kassierer", db_default="Kassierer"
    )
    files_members_group = models.CharField(
        "Gruppe für „Mitglieder“",
        max_length=64,
        blank=True,
        default="Mitglieder",
        db_default="Mitglieder",
    )
    # Fristen je Art in Jahren, abweichend von der Voreinstellung (0: dauerhaft)
    files_retention = models.JSONField("Fristen je Art", default=dict, blank=True, db_default={})
    # Freigaben, die HUBIplan angelegt hat: Ziel → {"group": …, "id": …}
    files_shares = models.JSONField(default=dict, blank=True, db_default={})
    # „Aus Nextcloud übernehmen“: Ordner, den der Verein dem Dienstkonto freigegeben hat
    files_source = models.CharField(
        "Ordner zum Übernehmen", max_length=300, blank=True, default="", db_default=""
    )
    files_error = models.CharField(max_length=500, blank=True, default="", db_default="")
    # Videoraum am Termin (Talk, siehe ``nc_talk``): Gespräch im Dienstkonto mit Link und
    # Passwort, nach dem Termin gelöscht
    talk_enabled = models.BooleanField("Videoraum am Termin", default=False, db_default=False)
    talk_keep_days = models.PositiveSmallIntegerField(
        "Videoraum löschen nach … Tagen", default=7, db_default=7
    )
    # Letzter Fehler oder Halt des Abgleichs (für die Oberfläche)
    sync_error = models.CharField(max_length=500, blank=True, default="")
    synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField("eingeschaltet", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField("zuletzt benutzt", null=True, blank=True)

    # Im Änderungsprotokoll nie Geheimnis oder Salz
    audit_fields = frozenset(
        {
            "name",
            "base_url",
            "client_id",
            "audience",
            "require_mfa",
            "require_pkce",
            "groups_board",
            "groups_roles",
            "groups_units",
            "groups_members",
            "usernames",
            "role_groups",
            "manage_accounts",
            "service_user",
            "account_group",
            "calendar_members",
            "calendar_members_group",
            "calendar_board",
            "calendar_board_group",
            "sync_groups",
            "sync_groups_list",
            "files_enabled",
            "files_root",
            "files_board_group",
            "files_finance_group",
            "files_members_group",
            "files_retention",
            "files_source",
            "talk_enabled",
            "talk_keep_days",
            "is_active",
        }
    )

    class Meta:
        verbose_name = "Nextcloud-Anmeldung"
        verbose_name_plural = "Nextcloud-Anmeldungen"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.host})"

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).netloc

    def set_secret(self) -> str:
        secret = secrets.token_urlsafe(32)
        self.secret_hash = hash_secret(secret)
        return secret

    def check_secret(self, secret: str) -> bool:
        return bool(self.secret_hash) and secrets.compare_digest(
            self.secret_hash, hash_secret(secret or "")
        )

    def groups_for_role(self, role_id: int) -> list[str]:
        return clean_groups((self.role_groups or {}).get(str(role_id)))

    def managed_groups(self) -> list[str]:
        """Gruppen, die der Abgleich setzen und entfernen darf: die Liste und die Kontengruppe;
        die Administratorgruppe nie."""
        groups = clean_groups(self.sync_groups_list)
        if self.account_group:
            groups = clean_groups([*groups, self.account_group])
        return [g for g in groups if g.casefold() not in {"admin"}]

    def blocked_usernames(self) -> frozenset[str]:
        """Benutzernamen, die nie zugeordnet werden: Verwaltung und Dienstkonto."""
        service = (self.service_user or "").strip().lower()
        return NEVER_USERNAMES | ({service} if service else set())

    def username_map(self) -> dict[str, str]:
        """E-Mail (klein) → Benutzername aus ``usernames``; ungültige und gesperrte Zeilen
        fallen weg (Gesamtaudit 15.11., AUTH-07)."""
        return {
            email: name
            for email, name, error in parse_usernames(self.usernames, self.blocked_usernames())
            if not error
        }

    @property
    def redirect_uris(self) -> list[str]:
        """Rückleitungen der Nextcloud-App „user_oidc“ (mit und ohne index.php)."""
        base = self.base_url.rstrip("/")
        return [f"{base}/apps/user_oidc/code", f"{base}/index.php/apps/user_oidc/code"]


class Account(models.Model):
    """Nextcloud-Konto, das sich über HUBIplan angemeldet hat.

    Nur diese Konten fasst der Abgleich an (deaktivieren und wieder aktivieren); ``admin``
    und Konten ohne Anmeldung über HUBIplan nie.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="accounts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    # Benutzername in der Nextcloud: bisheriger Name aus der Liste, sonst die Kennung ``sub``
    nc_user = models.CharField("Benutzername in der Nextcloud", max_length=64)
    first_login_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField()
    # Nur was HUBIplan selbst deaktiviert hat, aktiviert es wieder
    disabled_by_hubiplan = models.BooleanField(default=False)
    changed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True, default="")

    audit_fields = frozenset({"nc_user", "disabled_by_hubiplan"})

    class Meta:
        verbose_name = "Nextcloud-Konto"
        verbose_name_plural = "Nextcloud-Konten"
        ordering = ["nc_user"]
        constraints = [
            models.UniqueConstraint(fields=["client", "user"], name="oidc_account_unique_user"),
        ]

    def __str__(self) -> str:
        return self.nc_user


class CalendarItem(models.Model):
    """Termin, den HUBIplan in einen Nextcloud-Kalender geschrieben hat.

    ``digest`` ist die Prüfsumme des geschriebenen Inhalts: Nur Geändertes geht erneut hin,
    und was hier steht, aber nicht mehr dazugehört, wird dort gelöscht.
    """

    class Kind(models.TextChoices):
        MEMBERS = "members", gettext_lazy("Mitglieder")
        BOARD = "board", gettext_lazy("Vorstand")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="calendar_items")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Dateiname im Kalender, z. B. „hp-1a2b….ics“
    name = models.CharField(max_length=80)
    digest = models.CharField(max_length=64)
    written_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Termin in der Nextcloud"
        verbose_name_plural = "Termine in der Nextcloud"
        constraints = [
            models.UniqueConstraint(
                fields=["client", "kind", "name"], name="oidc_calendaritem_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class FileItem(models.Model):
    """Datei, die HUBIplan in einen Ordner der Nextcloud gelegt hat (für Frist und Protokoll)."""

    class Target(models.TextChoices):
        BOARD = "board", gettext_lazy("Vorstand")
        FINANCE = "finance", gettext_lazy("Kasse")
        MEMBERS = "members", gettext_lazy("Mitglieder")

    class Category(models.TextChoices):
        RECORDS = "records", gettext_lazy("Beschlüsse und Grundlagen")
        FINANCE = "finance", gettext_lazy("Kassen- und Steuerunterlagen")
        STATISTICS = "statistics", gettext_lazy("Planung und Statistik ohne Personen")
        REPORTS = "reports", gettext_lazy("Meldungen an Verbände")
        PERSONAL = "personal", gettext_lazy("Personenbezogene Listen")
        OTHER = "other", gettext_lazy("Sonstiges")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="file_items")
    target = models.CharField(max_length=10, choices=Target.choices)
    category = models.CharField(max_length=12, choices=Category.choices)
    # Pfad im Dienstkonto, z. B. „HUBIplan/Kasse/kassenbericht-2026.pdf“
    path = models.CharField(max_length=400)
    size = models.PositiveBigIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Leer: dauerhaft
    delete_after = models.DateField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    audit_fields = frozenset({"path", "target", "category", "delete_after"})

    class Meta:
        verbose_name = "Datei in der Nextcloud"
        verbose_name_plural = "Dateien in der Nextcloud"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.path


class TalkRoom(models.Model):
    """Videoraum (Talk-Gespräch im Dienstkonto) zu einem Termin; nach dem Termin gelöscht."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="talk_rooms")
    # Leer: Termin gelöscht, der Raum geht beim nächsten Aufräumen weg
    event = models.OneToOneField(
        "events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="talk_room"
    )
    token = models.CharField(max_length=64)
    # Passwort des Links, verschlüsselt (``accounts.mfa.encrypt``, Zweck „nextcloud“)
    password = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    audit_fields = frozenset({"token"})

    class Meta:
        verbose_name = "Videoraum"
        verbose_name_plural = "Videoräume"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.token

    @property
    def url(self) -> str:
        return f"{self.client.base_url.rstrip('/')}/call/{self.token}"
