import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext


def generate_initial_password(length: int = 16) -> str:
    """Zufallspasswort (nur noch für Testdaten; Konten bekommen Einladungslinks, FQ-16)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserManager(BaseUserManager):
    """Manager für Benutzer mit E-Mail-Adresse als Login (kein Benutzername)."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError(gettext("Eine E-Mail-Adresse ist erforderlich."))
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError(gettext("Superuser brauchen is_staff=True und is_superuser=True."))
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Plattform-Benutzerkonto. Login ist die E-Mail-Adresse.

    Ein Konto ist nicht dasselbe wie ein Vereinsmitglied: Mitglieder (Personen)
    und ihre Rollen je Organisation kommen in späteren Meilensteinen dazu.
    """

    username = None
    email = models.EmailField("E-Mail-Adresse", unique=True)
    # Lernhilfen: Hauptschalter und die „Warum?“-Erklärungen, die der Nutzer
    # ausgeblendet hat (nur Schlüssel). Reine Anzeigepräferenz.
    learning_aids = models.BooleanField("Lernhilfen zeigen", default=True)
    learning_hidden = models.JSONField("ausgeblendete Erklärungen", null=True, blank=True)
    # Hilfe: abgehakte „Erste Schritte“ (nur Schlüssel der Anleitungen, nichts ausgewertet)
    help_done = models.JSONField("erledigte erste Schritte", null=True, blank=True)
    # Nutzersprache (konzepte/englisch.md): Oberfläche, Fehlermeldungen, Hinweis-Mails und
    # Push an dieses Konto. Belege und Briefe folgen der Vereinssprache der Einheit.
    language = models.CharField(
        "Sprache", max_length=5, choices=settings.LANGUAGES, default="de", db_default="de"
    )
    # Darstellung der Web-App (konzepte/dunkelmodus-web.md, X-02): wie das Gerät, hell oder
    # dunkel. Im Konto gespeichert, damit sie auf allen Geräten gilt. Reine Anzeigepräferenz.
    color_scheme = models.CharField(
        "Darstellung",
        max_length=5,
        choices=[("auto", "Wie Gerät"), ("light", "Hell"), ("dark", "Dunkel")],
        default="auto",
        db_default="auto",
    )
    # Startseite (S-04): ausgeblendete Schnellaktionen, Schlüssel wie im Frontend; "*" blendet
    # den ganzen Block aus. Reine Anzeigepräferenz, null = alle zeigen.
    home_actions_hidden = models.JSONField("ausgeblendete Schnellaktionen", null=True, blank=True)
    # Eigene Auswahl und Reihenfolge der Schnellaktionen je Arbeitsbereich ("o12" Einheit,
    # "d5" Untereinheit), z. B. {"o12": ["termin", "aufgabe"]}. Fehlt ein Bereich, gilt der
    # Vorschlag aus den Rollen. Reine Anzeigepräferenz.
    home_actions = models.JSONField("Auswahl der Schnellaktionen", null=True, blank=True)
    # Eigene Anordnung der Startseiten-Blöcke je Arbeitsbereich, z. B. {"o12": {"order":
    # ["termine", "schnellaktionen"], "hidden": ["hinweise"], "wide": ["termine"]}}. Fehlt ein
    # Bereich, gilt die Standardanordnung. Reine Anzeigepräferenz.
    home_layout = models.JSONField("Anordnung der Startseite", null=True, blank=True)
    # Gesetzt, solange das Konto noch das ausgegebene Startpasswort hat: Es muss bei der
    # ersten Anmeldung ersetzt werden und wird nach Ablauf unbrauchbar (AT-S04)
    initial_password_expires = models.DateTimeField(
        "Startpasswort gültig bis", null=True, blank=True
    )
    # Pflicht-2FA (Gesamtaudit 31.10.b, Frage 1): bis dahin einrichten, sonst ruhen heikle Rechte
    mfa_required_by = models.DateTimeField(
        "Zwei-Faktor-Anmeldung einrichten bis", null=True, blank=True
    )
    auth_version = models.PositiveBigIntegerField(default=0, db_default=0, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"

    def __str__(self) -> str:
        return self.email

    def set_password(self, raw_password) -> None:
        # Jedes selbst gesetzte Passwort (Mein Konto, Zurücksetzen) ersetzt das Startpasswort
        super().set_password(raw_password)
        self.initial_password_expires = None
        self._password_write_requested = True

    def set_unusable_password(self) -> None:
        super().set_unusable_password()
        self._password_write_requested = True

    def _get_session_auth_hash(self, secret=None):
        original = super()._get_session_auth_hash(secret=secret)
        # Bestehende Sitzungen bleiben bis zur ersten Sicherheitsänderung gültig.
        if not self.auth_version:
            return original
        return salted_hmac(
            "accounts.User.auth_version",
            f"{original}:{self.auth_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    def save(self, *args, **kwargs):
        fields = kwargs.get("update_fields")
        if not self._state.adding and not kwargs.get("force_insert"):
            # Ausschließlich security.secure_account erhöht diese Spalte unter
            # Zeilensperre. Ein vor Recovery geladenes Objekt darf sie beim späteren
            # vollständigen Speichern seiner Profilfelder nicht zurücksetzen.
            if fields is None:
                fields = {
                    field.attname
                    for field in self._meta.concrete_fields
                    if not field.primary_key and field.attname in self.__dict__
                }
                if not getattr(self, "_password_write_requested", False):
                    # Profilvollsave: ein übernommener Hash/Startpasswortstatus ist
                    # kein Passwortwechsel. Explizite Setter oder update_fields
                    # bleiben die absichtlichen Passwort-Schreibwege.
                    fields -= {"password", "initial_password_expires"}
            kwargs["update_fields"] = fields = set(fields) - {"auth_version"}
        if fields is not None and "password" in fields:
            kwargs["update_fields"] = {*fields, "initial_password_expires"}
        writes_password = fields is None or "password" in fields
        super().save(*args, **kwargs)
        if writes_password:
            self._password_write_requested = False

    @property
    def must_change_password(self) -> bool:
        return self.initial_password_expires is not None


class EmailChange(models.Model):
    """Bestätigungslink für eine neue Anmelde-E-Mail (nur der Hash des Tokens)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_changes")
    new_email = models.EmailField("neue E-Mail-Adresse")
    token_hash = models.CharField(max_length=64, unique=True)
    # Konten ohne Passwort bestätigen den Wechsel auch über die bisherige Adresse
    # (Gesamtaudit 05.11. GA-10); leer: nicht nötig.
    old_token_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    new_confirmed_at = models.DateTimeField(null=True, blank=True)
    old_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "E-Mail-Änderung"
        verbose_name_plural = "E-Mail-Änderungen"

    def __str__(self) -> str:
        return f"{self.user} → {self.new_email}"


class StoredSignature(models.Model):
    """Hinterlegte Unterschrift einer Person (Mein Konto › Unterschrift).

    Nur die Form (Linienzüge, siehe finance/signature.py). Verwendet wird sie nur, wenn die
    Person selbst eine Quittung abschließt."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="stored_signature"
    )
    strokes = models.JSONField("Unterschrift")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "hinterlegte Unterschrift"
        verbose_name_plural = "hinterlegte Unterschriften"

    def __str__(self) -> str:
        return f"Unterschrift {self.user_id}"
