"""Hinweismails bei Änderungen an den Anmeldedaten (Gesamtaudit 15.11., AUTH-09).

Die Mail nennt nur, was sich geändert hat, und was zu tun ist, wenn man es nicht selbst war.
Sie enthält keine Geheimnisse und keinen Link zum Bestätigen. Versendet wird als Art
„sicherheit“ (Vorrang im Mailbudget) in der Sprache des Kontos, nach dem Speichern.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils.translation import gettext_noop

log = logging.getLogger(__name__)

TOTP_ADDED = (
    gettext_noop("Zwei-Faktor-Anmeldung eingerichtet"),
    gettext_noop("Für deinen HUBIplan-Zugang wurde eine Authenticator-App eingerichtet."),
)
TOTP_REMOVED = (
    gettext_noop("Zwei-Faktor-Anmeldung entfernt"),
    gettext_noop("Die Authenticator-App wurde aus deinem HUBIplan-Zugang entfernt."),
)
RECOVERY_REMOVED = (
    gettext_noop("Wiederherstellungscodes entfernt"),
    gettext_noop("Die Wiederherstellungscodes deines HUBIplan-Zugangs wurden entfernt."),
)
RECOVERY_RESET = (
    gettext_noop("Neue Wiederherstellungscodes"),
    gettext_noop(
        "Für deinen HUBIplan-Zugang wurden neue Wiederherstellungscodes erzeugt. Die bisherigen "
        "gelten nicht mehr."
    ),
)
EMAIL_CHANGED = (
    gettext_noop("Anmelde-E-Mail geändert"),
    gettext_noop("Die Anmelde-E-Mail deines HUBIplan-Zugangs lautet jetzt {new}."),
)


def notify(user, message: tuple[str, str], recipients: list[str] | None = None, **values) -> None:
    """Hinweis an das Konto (oder ``recipients``), nach dem Speichern."""
    to = [a for a in (recipients or [getattr(user, "email", "")]) if a]
    if not to:
        return

    def send() -> None:
        from django.utils import timezone
        from django.utils.translation import gettext as _

        from core.i18n import datetime_text, language_of, user_language
        from outbox.mail import send as send_mail

        with language_of(user):
            subject = _(message[0])
            body = _(
                "Hallo {name},\n\n{text}\n\nZeit: {when} Uhr\n\n"
                "Warst du das, ist nichts zu tun. Sonst melde dich bitte sofort an, ändere dein "
                "Passwort und prüfe unter Mein Konto › Anmeldung & Sicherheit die "
                "Zwei-Faktor-Anmeldung. Sag außerdem dem Vorstand Bescheid.\n"
            ).format(
                name=user.get_full_name() or user.email,
                text=_(message[1]).format(**values),
                when=datetime_text(timezone.localtime()),
            )
        for address in dict.fromkeys(to):
            try:
                send_mail(
                    [address],
                    subject,
                    body,
                    kind="sicherheit",
                    fail_silently=True,
                    language=user_language(user),
                )
            except Exception:  # noqa: BLE001 – eine Mail darf die Änderung nie verhindern
                log.exception("Sicherheitshinweis nicht gesendet")

    transaction.on_commit(send)


def _on_added(sender, request=None, user=None, authenticator=None, **kwargs):
    from allauth.mfa.models import Authenticator

    if authenticator is not None and authenticator.type == Authenticator.Type.TOTP:
        notify(user, TOTP_ADDED)


def _on_removed(sender, request=None, user=None, authenticator=None, **kwargs):
    from allauth.mfa.models import Authenticator

    if authenticator is None:
        return
    if authenticator.type == Authenticator.Type.TOTP:
        notify(user, TOTP_REMOVED)
    elif authenticator.type == Authenticator.Type.RECOVERY_CODES:
        notify(user, RECOVERY_REMOVED)


def _on_reset(sender, request=None, user=None, authenticator=None, **kwargs):
    notify(user, RECOVERY_RESET)


def connect() -> None:
    from allauth.mfa import signals

    signals.authenticator_added.connect(_on_added, dispatch_uid="hinweis-2fa-added")
    signals.authenticator_removed.connect(_on_removed, dispatch_uid="hinweis-2fa-removed")
    signals.authenticator_reset.connect(_on_reset, dispatch_uid="hinweis-2fa-reset")
