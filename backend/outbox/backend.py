"""E-Mail-Backend, das jede Nachricht im Postausgang speichert.

- Ohne ``EMAIL_HOST``: Die Mail wird nur gespeichert (Test-Postfach).
- Mit ``EMAIL_HOST``: zusätzlich per SMTP versendet; der Status wird vermerkt.

Organisation und Art einer Mail kommen über die Kopfzeilen ``X-Hubiplan-Org``
und ``X-Hubiplan-Kind`` (siehe ``outbox.mail.send``); sie werden vor dem
Versand entfernt.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend
from django.utils.translation import gettext

from core.tenancy import rls_bypass

from .models import OutgoingMail

logger = logging.getLogger(__name__)

ORG_HEADER = "X-Hubiplan-Org"
KIND_HEADER = "X-Hubiplan-Kind"


def attachment_dir() -> Path:
    return Path(settings.PRIVATE_ROOT) / "outbox"


def _store_attachments(message, org_id: int | None) -> list[dict]:
    """Anhänge verschlüsselt im privaten Speicher ablegen (Schlüssel des Vereins,
    ohne Verein der Plattform)."""
    from django.core.files.base import ContentFile

    from core import crypto
    from exchange.models import private_storage
    from organizations.models import Organization

    stored = []
    if not message.attachments:
        return stored
    owner = org_id if org_id is not None else Organization.platform().pk
    for item in message.attachments:
        if isinstance(item, tuple):
            name, content, mimetype = item
        else:  # MIMEBase
            name = item.get_filename() or "anhang"
            content = item.get_payload(decode=True)
            mimetype = item.get_content_type()
        if isinstance(content, str):
            content = content.encode()
        relative = f"outbox/{uuid.uuid4().hex}-{Path(name).name}"
        with crypto.owner(owner):
            relative = private_storage().save(relative, ContentFile(content or b""))
        stored.append(
            {
                "name": name,
                "path": relative,
                "size": len(content or b""),
                "content_type": mimetype or "application/octet-stream",
            }
        )
    return stored


class NotAccepted(Exception):
    """Der Mailserver hat eine Nachricht nicht angenommen."""


# Links, mit denen man sich anmelden, abstimmen oder fremde Vorgänge bearbeiten kann. Sie stehen
# nur in der verschickten Mail, nie im Postausgang, den der Vorstand lesen kann.
SECRET_LINK = re.compile(
    # Alles, was ein Geheimnis im Pfad trägt (Gesamtaudit 05.11. GA-04 + Sicherheitsprüfung)
    r"(https?://\S*?/(?:anmelden/link|passwort-zuruecksetzen|konto/email|foto|ausweis"
    r"|rundschreiben/bestaetigen|rundschreiben/abmelden"
    r"|umfrage|rueckmeldung|anmeldung/bestaetigen|meine-anmeldung|antrag|nachweis"
    r"|auslage|bilder-hochladen|mitglied-werden/stand)/)\S+"
)
REDACTED = "[Link aus Sicherheitsgründen nicht gespeichert]"
# Signierte Plus-Antwortadressen (z. B. termin+<id>-<mid>-<hex>@… oder …+nw<key>@…)
SECRET_REPLY_TAG = re.compile(r"([A-Za-z0-9._-]+)\+[^\s,@<>]+(@[^\s,<>]+)")


def redact(text: str) -> str:
    text = SECRET_LINK.sub(lambda m: m.group(1) + REDACTED, text or "")
    return re.sub(r"(https?://\S*?/musik-gast#)\S+", lambda m: m.group(1) + REDACTED, text)


def redact_reply_to(addresses: list[str] | None) -> str:
    raw = ", ".join(addresses or [])
    return SECRET_REPLY_TAG.sub(r"\1+[gekürzt]\2", raw)


def transient(exc: BaseException) -> bool:
    """Hat der Mailserver die Mail sicher nicht angenommen und nur vorübergehend abgelehnt?

    Nur dann darf wiederholt werden (Gesamtaudit 15.11., PF-09): Verbindungsaufbau gescheitert
    (vor jedem Senden) oder eine ausdrückliche 4xx-Antwort. Bricht die Verbindung während des
    Sendens ab, ist offen, ob die Mail angenommen wurde; dann wird nicht wiederholt, lieber eine
    Mail zu wenig als doppelt."""
    import smtplib

    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        return bool(codes) and all(400 <= code < 500 for code in codes)
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return False


class _ConnectFailed(Exception):
    """Interner Hinweis: Verbindung kam nicht zustande, es wurde nichts gesendet."""


class OutboxBackend(BaseEmailBackend):
    """Speichert jede Mail im Postausgang und sendet sie per SMTP (falls eingerichtet).

    Mit ``open()`` (z. B. über ``outbox.mail.connection()``) bleibt die SMTP-Verbindung für
    viele Mails offen; vor jeder weiteren Mail prüft ``NOOP``, ob sie noch steht, sonst wird
    neu verbunden, bevor etwas gesendet ist. Vorübergehende Ablehnungen (4xx) und ein
    gescheiterter Verbindungsaufbau werden mit Wartezeit wiederholt (``MAIL_RETRY_DELAYS``)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smtp = None
        self._keep_open = False

    def open(self):
        self._keep_open = True
        return False

    def close(self):
        self._keep_open = False
        self._drop()

    def _drop(self):
        if self._smtp is not None:
            try:
                getattr(self._smtp, "close", lambda: None)()
            except Exception:  # noqa: BLE001 – Verbindung ist ohnehin weg
                logger.debug("SMTP-Verbindung ließ sich nicht sauber schließen", exc_info=True)
            self._smtp = None

    def _connection(self):
        """Offene, lebende SMTP-Verbindung; wirft, wenn der Aufbau scheitert (nichts gesendet)."""
        if self._smtp is not None and getattr(self._smtp, "connection", None) is not None:
            try:
                status = self._smtp.connection.noop()[0]
            except Exception:  # noqa: BLE001
                status = None
            if status == 250:
                return self._smtp
            self._drop()
        smtp = SmtpBackend(fail_silently=False)
        opener = getattr(smtp, "open", None)
        if opener is not None:
            opener()
        self._smtp = smtp
        return smtp

    def _send_smtp(self, message) -> None:
        import smtplib
        import time

        delays = list(getattr(settings, "MAIL_RETRY_DELAYS", (2, 10)))
        attempt = 0
        while True:
            try:
                try:
                    smtp = self._connection()
                except (OSError, smtplib.SMTPException) as exc:
                    # Aufbau gescheitert: Die Mail ist sicher nicht gesendet
                    raise _ConnectFailed() from exc
                accepted = smtp.send_messages([message])
                if not accepted:
                    raise NotAccepted("Der Mailserver hat die Nachricht nicht angenommen.")
                return
            except _ConnectFailed as wrapped:
                error: BaseException = wrapped.__cause__ or wrapped
                retry = True
            except Exception as exc:  # noqa: BLE001
                error = exc
                retry = transient(exc)
                # Nach einem Fehler beim Senden die Verbindung nicht weiterverwenden
                self._drop()
            if not retry or attempt >= len(delays):
                raise error
            logger.warning("Versand vorübergehend abgelehnt, neuer Versuch in %ss", delays[attempt])
            time.sleep(delays[attempt])
            attempt += 1

    def send_messages(self, email_messages) -> int:
        count = 0
        try:
            for message in email_messages:
                count += self._send_one(message)
        finally:
            if not self._keep_open:
                self._drop()
        return count

    def _send_one(self, message) -> int:
        headers = message.extra_headers or {}
        org_id = headers.pop(ORG_HEADER, None)
        kind = headers.pop(KIND_HEADER, "")
        body = message.body
        for alt in getattr(message, "alternatives", []) or []:
            if not body and alt[1] == "text/plain":
                body = alt[0]
        org_pk = int(org_id) if org_id else None
        private_task = kind == "aufgabe"
        anon_survey = kind == "umfrage_anonym"
        # Köderdaten (organizations.decoys): nie versenden, aber melden
        from organizations import decoys

        if decoys.check_outgoing([*message.to, *message.cc, *message.bcc], message.subject):
            return 1
        with rls_bypass():
            mail = OutgoingMail.objects.create(
                organization_id=org_pk,
                to=gettext("[Empfänger anonymisiert]")
                if anon_survey
                else ", ".join([*message.to, *message.cc, *message.bcc]),
                reply_to=redact_reply_to(message.reply_to),
                subject=gettext("Aufgabenbenachrichtigung")
                if private_task
                else message.subject[:300],
                body=gettext("Inhalt nur an das empfangende Konto versandt.")
                if (private_task or anon_survey)
                else redact(body),
                attachments=getattr(message, "outbox_attachments", None)
                or _store_attachments(message, org_pk),
                kind=kind[:50],
            )
        if not settings.EMAIL_HOST:
            return 1
        try:
            self._send_smtp(message)
            mail.status = OutgoingMail.Status.SENT
        except Exception as exc:  # noqa: BLE001 – Fehler vermerken, nicht abbrechen
            logger.exception("Versand an %s fehlgeschlagen", mail.to)
            mail.status = OutgoingMail.Status.FAILED
            mail.error = gettext("Versand fehlgeschlagen") if private_task else str(exc)[:300]
            with rls_bypass():
                mail.save(update_fields=["status", "error"])
            if not self.fail_silently:
                raise
            return 0  # nicht als versandt zählen
        with rls_bypass():
            mail.save(update_fields=["status", "error"])
        return 1
