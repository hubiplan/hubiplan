"""Rechnungspostfach: E-Rechnungen aus Mails in den Rechnungseingang übernehmen (#374).

Je Server gibt es ein Postfach (``EINVOICE_IMAP_*`` in der ``.env``). Jeder Verein hat
eine Plus-Adresse mit zufälliger Kennung, z. B. ``rechnung+k7m2q9ab@example.org``. Ein
Celery-Job holt das Postfach jede Minute ab:

- Mails an eine bekannte Plus-Adresse: XML-Anhänge und PDF-Anhänge mit eingebettetem XML
  (ZUGFeRD/Factur-X) gehen nach der Virenprüfung denselben Weg wie beim Hochladen
  (``incoming_import.store``: Original, Prüfung im Hintergrund, Dublettenschutz). Die Mail
  wandert danach in den Ordner ``EINVOICE_IMAP_DONE_FOLDER``.
- Mails ohne E-Rechnung, Spam und Mails mit Schadsoftware bleiben (gelesen) im Postfach
  und erscheinen im Rechnungseingang des Vereins als Hinweis.
- Mails an keine bekannte Adresse bleiben gelesen im Postfach; sie gehören keinem Verein.
- Ist der Virenscanner nicht erreichbar, bleibt die Mail ungelesen und kommt beim
  nächsten Abruf wieder dran.

Angenommen wird jeder Absender (Ralf 10.11.2026). Passt er zu keiner E-Mail-Adresse
eines Geschäftspartners, zeigt der Rechnungseingang das deutlich an; geprüft wird bei der
fachlichen Freigabe.
"""

from __future__ import annotations

import datetime
import hashlib
import imaplib
import logging
import re
import secrets
import ssl
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import virenscan
from core.tenancy import rls_bypass, tenant_context

from . import incoming_import
from .models import IncomingMail, IncomingMailbox

logger = logging.getLogger(__name__)

MAX_RAW_BYTES = 25 * 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_ATTACHMENTS = 10
FETCH_BATCH = 50
LOCK = "billing:incoming_mail:fetch"
TAG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TAG_LENGTH = 10
TAG_RE = re.compile(r"\+([a-z0-9]{6,20})$")
RETENTION_DAYS = 90


class Result:
    """Ausgang einer Mail für den Abruf: verschieben, liegen lassen oder später erneut."""

    MOVE = "move"
    KEEP = "keep"


# --- Adresse je Verein ---


def configured() -> bool:
    return bool(settings.EINVOICE_IMAP_HOST)


def mailbox_address() -> str:
    """Grundadresse des Postfachs, z. B. rechnung@example.org (leer ohne Postfach)."""
    if not configured():
        return ""
    return (settings.EINVOICE_IMAP_ADDRESS or settings.EINVOICE_IMAP_USER).strip().lower()


def _new_tag() -> str:
    return "".join(secrets.choice(TAG_ALPHABET) for _ in range(TAG_LENGTH))


def mailbox_of(org, renew: bool = False) -> IncomingMailbox:
    """Kennung des Vereins; legt sie beim ersten Aufruf an. ``renew``: neue Kennung."""
    box = IncomingMailbox.objects.filter(organization=org).first()
    if box is not None and not renew:
        return box
    for _ in range(5):
        try:
            with transaction.atomic():
                if box is None:
                    return IncomingMailbox.objects.create(organization=org, tag=_new_tag())
                box.tag = _new_tag()
                box.save(update_fields=["tag"])
                return box
        except IntegrityError:
            box = IncomingMailbox.objects.filter(organization=org).first()
            if box is not None and not renew:
                return box
    raise RuntimeError("Keine freie Kennung für das Rechnungspostfach gefunden.")


def address_for(org) -> str:
    """Plus-Adresse des Vereins (leer ohne Postfach)."""
    base = mailbox_address()
    if "@" not in base:
        return ""
    local, domain = base.split("@", 1)
    return f"{local}+{mailbox_of(org).tag}@{domain}"


def recipient_addresses(msg: EmailMessage) -> list[str]:
    headers = []
    for name in ("Delivered-To", "X-Original-To", "Envelope-To", "To", "Cc"):
        headers.extend(str(v) for v in msg.get_all(name) or [])
    return [a.strip().lower() for _, a in getaddresses(headers) if a]


def find_org_id(addresses: list[str]) -> int | None:
    """Verein zur Plus-Adresse; nur Adressen mit der Domain des Postfachs zählen."""
    base = mailbox_address()
    if "@" not in base:
        return None
    base_local, domain = base.split("@", 1)
    for address in addresses:
        if "@" not in address:
            continue
        local, at_domain = address.rsplit("@", 1)
        if at_domain != domain or not local.startswith(f"{base_local}+"):
            continue
        found = TAG_RE.search(local)
        if not found:
            continue
        with rls_bypass():
            org_id = (
                IncomingMailbox.objects.filter(tag=found.group(1))
                .values_list("organization_id", flat=True)
                .first()
            )
        if org_id:
            return org_id
    return None


# --- Eine Mail ---


def spam_flagged(msg: EmailMessage) -> bool:
    flag = str(msg.get("X-Spam-Flag", "") or "").strip().lower()
    status = str(msg.get("X-Spam-Status", "") or "").strip().lower()
    return flag == "yes" or status.startswith("yes")


def _known_sender(org, sender: str) -> bool:
    from .incoming_partner import known_sender

    return known_sender(org, sender)


def _is_xml(name: str, content_type: str, data: bytes) -> bool:
    head = data[:200].lstrip(b"\xef\xbb\xbf \t\r\n")
    return (
        name.lower().endswith(".xml") or content_type in ("application/xml", "text/xml")
    ) and head.startswith(b"<")


def _attachments(msg: EmailMessage) -> tuple[list[tuple[str, bytes]], list[dict], bool]:
    """E-Rechnungen unter den Anhängen, übersprungene Anhänge mit Grund, Schadsoftware ja/nein.

    Gründe (Oberfläche übersetzt sie): other, too_big, too_many, plain_pdf, virus.

    ``virenscan.ScanUnavailable`` geht weiter: Die Mail bleibt dann ungelesen liegen.
    """
    from finance import einvoice

    found: list[tuple[str, bytes]] = []
    skipped: list[dict] = []
    virus = False
    for part in msg.iter_attachments():
        name = incoming_import.safe_name(part.get_filename() or "")
        content_type = part.get_content_type()
        data = part.get_payload(decode=True) or b""
        if not data:
            continue
        is_pdf = data.startswith(b"%PDF")
        if not is_pdf and not _is_xml(name, content_type, data):
            if part.get_filename():
                skipped.append({"name": name, "reason": "other"})
            continue
        if len(data) > incoming_import.MAX_BYTES:
            skipped.append({"name": name, "reason": "too_big"})
            continue
        if len(found) >= MAX_ATTACHMENTS:
            skipped.append({"name": name, "reason": "too_many"})
            continue
        if is_pdf and not einvoice.xml_from_pdf(data):
            # Gewöhnliche PDF-Rechnung oder Anschreiben: keine E-Rechnung
            skipped.append({"name": name, "reason": "plain_pdf"})
            continue
        if not virenscan.inbound_ok(data, name, "Mail an das Rechnungspostfach"):
            skipped.append({"name": name, "reason": "virus"})
            virus = True
            continue
        found.append((name, data))
    return found, skipped, virus


def process_message(raw: bytes) -> str:
    """Eine Mail verarbeiten. Gibt zurück, ob sie verschoben werden kann oder liegen bleibt."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    org_id = find_org_id(recipient_addresses(msg))
    if org_id is None:
        logger.warning("Rechnungspostfach: Mail ohne bekannte Empfängeradresse bleibt liegen")
        return Result.KEEP
    from organizations.models import Organization

    with rls_bypass():
        org = Organization.objects.get(pk=org_id)
    with tenant_context(org_id):
        return _process_for(org, msg)


def _process_for(org, msg: EmailMessage) -> str:
    message_id = str(msg.get("Message-ID", "") or "").strip()
    message_hash = hashlib.sha256(message_id.encode()).hexdigest() if message_id else ""
    if (
        message_hash
        and IncomingMail.objects.filter(organization=org, message_hash=message_hash).exists()
    ):
        return Result.MOVE  # schon verarbeitet (z. B. Abbruch nach dem Speichern)
    sender = parseaddr(str(msg.get("From", "") or ""))[1].strip().lower()[:254]
    subject = re.sub(r"\s+", " ", str(msg.get("Subject", "") or "")).strip()[:300]
    entry = {
        "organization": org,
        "message_hash": message_hash,
        "sender": sender,
        "subject": subject,
        "sender_known": _known_sender(org, sender),
    }
    if spam_flagged(msg):
        IncomingMail.objects.create(**entry, status=IncomingMail.Status.SPAM)
        return Result.KEEP
    found, skipped, virus = _attachments(msg)
    if not found:
        status = IncomingMail.Status.VIRUS if virus else IncomingMail.Status.NO_INVOICE
        IncomingMail.objects.create(**entry, status=status, skipped=skipped)
        return Result.KEEP
    try:
        with transaction.atomic():
            mail = IncomingMail.objects.create(
                **entry,
                status=IncomingMail.Status.IMPORTED,
                skipped=skipped,
                # Mit übersprungener Schadsoftware bleibt der Hinweis offen
                dismissed_at=None if virus else timezone.now(),
            )
            for name, data in found:
                item, created = incoming_import.store(org, data, name, mail=mail)
                if not created and item.mail_id is None:
                    item.mail = mail
                    item.save(update_fields=["mail"])
    except Exception:  # noqa: BLE001 - als Hinweis zeigen, Mail bleibt im Postfach
        logger.exception("Rechnungspostfach: Anhänge für Einheit %s nicht übernommen", org.pk)
        failed = [{"name": name, "reason": "error"} for name, _ in found]
        IncomingMail.objects.create(**entry, status=IncomingMail.Status.ERROR, skipped=failed)
        return Result.KEEP
    return Result.KEEP if virus else Result.MOVE


def reject_oversized(header: bytes) -> str:
    """Zu große Mail nur anhand ihres Kopfs als Hinweis eintragen; sie bleibt liegen."""
    msg = BytesParser(policy=policy.default).parsebytes(header, headersonly=True)
    org_id = find_org_id(recipient_addresses(msg))
    if org_id is None:
        return Result.KEEP
    from organizations.models import Organization

    with rls_bypass():
        org = Organization.objects.get(pk=org_id)
    with tenant_context(org_id):
        sender = parseaddr(str(msg.get("From", "") or ""))[1].strip().lower()[:254]
        IncomingMail.objects.create(
            organization=org,
            sender=sender,
            subject=re.sub(r"\s+", " ", str(msg.get("Subject", "") or "")).strip()[:300],
            sender_known=_known_sender(org, sender),
            status=IncomingMail.Status.ERROR,
            skipped=[{"name": "", "reason": "mail_too_big"}],
        )
    return Result.KEEP


# --- Abholen per IMAP ---


def _size_of(info) -> int | None:
    for part in info or []:
        line = part[0] if isinstance(part, tuple) else part
        if isinstance(line, bytes):
            found = re.search(rb"RFC822\.SIZE (\d+)", line)
            if found:
                return int(found.group(1))
    return None


def _quoted(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _move(imap, uid: bytes, folder: str) -> bool:
    """Mail in den Ordner „verarbeitet“ verschieben; False, wenn das nicht geht."""
    if not folder:
        return False
    target = _quoted(folder)
    typ, _ = imap.uid("copy", uid, target)
    if typ != "OK":
        imap.create(target)
        typ, _ = imap.uid("copy", uid, target)
    if typ != "OK":
        logger.warning("Rechnungspostfach: Ordner %s nicht nutzbar", folder)
        return False
    imap.uid("store", uid, "+FLAGS", "(\\Deleted)")
    return True


def fetch() -> int:
    """Neue Mails aus dem Rechnungspostfach abholen. Gibt die Anzahl verarbeiteter Mails."""
    if not configured():
        return 0
    if not cache.add(LOCK, 1, timeout=10 * 60):
        return 0  # läuft schon
    done = 0
    try:
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(
            settings.EINVOICE_IMAP_HOST,
            settings.EINVOICE_IMAP_PORT,
            ssl_context=context,
            timeout=60,
        ) as imap:
            imap.login(settings.EINVOICE_IMAP_USER, settings.EINVOICE_IMAP_PASSWORD)
            imap.select(_quoted(settings.EINVOICE_IMAP_FOLDER))
            _, found = imap.uid("search", None, "UNSEEN")
            moved = False
            for uid in (found[0] or b"").split()[:FETCH_BATCH]:
                # Erst die Größe, dann höchstens MAX_RAW_BYTES + 1 Byte laden
                _, info = imap.uid("fetch", uid, "(RFC822.SIZE)")
                size = _size_of(info)
                too_big = size is not None and size > MAX_RAW_BYTES
                what = (
                    f"(BODY.PEEK[HEADER]<0.{MAX_HEADER_BYTES}>)"
                    if too_big
                    else f"(BODY.PEEK[]<0.{MAX_RAW_BYTES + 1}>)"
                )
                _, parts = imap.uid("fetch", uid, what)
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if raw is None:
                    continue
                try:
                    if too_big or len(raw) > MAX_RAW_BYTES:
                        result = reject_oversized(raw[:MAX_HEADER_BYTES])
                    else:
                        result = process_message(raw)
                except virenscan.ScanUnavailable:
                    # Anhänge nicht prüfbar: Mail bleibt ungelesen, weitere später
                    logger.warning("Rechnungspostfach: Virenprüfung aus, Mail %s bleibt", uid)
                    break
                except Exception:  # noqa: BLE001
                    logger.exception("Rechnungspostfach: Mail %s nicht verarbeitet", uid)
                    result = Result.KEEP
                done += 1
                imap.uid("store", uid, "+FLAGS", "(\\Seen)")
                if result == Result.MOVE:
                    moved = _move(imap, uid, settings.EINVOICE_IMAP_DONE_FOLDER) or moved
            if moved:
                imap.expunge()
    except (OSError, imaplib.IMAP4.error):
        logger.exception("Rechnungspostfach nicht erreichbar")
    finally:
        cache.delete(LOCK)
    return done


def purge_old() -> int:
    """Einträge des Rechnungspostfachs nach ``RETENTION_DAYS`` Tagen löschen."""
    cutoff = timezone.now() - datetime.timedelta(days=RETENTION_DAYS)
    with rls_bypass():
        # Mails mit übernommenen Rechnungen bleiben, solange es die Rechnungen gibt
        old = IncomingMail.objects.filter(received_at__lt=cutoff, invoices__isnull=True)
        count, _ = old.delete()
    return count
