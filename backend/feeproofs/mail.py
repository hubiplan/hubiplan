"""Nachweis per Antwort auf die Erinnerungsmail (über das Postfach des Rechnungseingangs).

Jede Erinnerung trägt eine persönliche Antwortadresse ``<postfach>+nw<Kennung>@<domain>``. Der
Abruf des Rechnungspostfachs (``billing/incoming_mail.py``) gibt Mails an solche Adressen
hierher. Die Kennung gehört zu genau einem ``ProofLink`` und damit zu Mitglied, Ermäßigung und
Beitragsjahr; eine Zuordnung nach Absender ist nicht nötig.

PDF- und Bildanhänge werden nach der Virenprüfung zu Nachweisen (höchstens drei je Mail).
Ohne passenden Anhang entsteht ein Nachweis ohne Datei mit dem Betreff als Nachricht, damit
der Vorstand die Mail nicht übersieht. Der Mailtext selbst wird nicht gespeichert.
"""

from __future__ import annotations

import logging
import re
from email.message import EmailMessage

from django.utils import timezone

from core import virenscan
from core.tenancy import rls_bypass, tenant_context

from . import services
from .models import FeeProof, ProofLink

logger = logging.getLogger(__name__)

KEY_RE = re.compile(r"\+nw([a-z0-9]{8,20})$")
MAX_ATTACHMENTS = 3


def link_for(addresses: list[str]) -> ProofLink | None:
    from billing.incoming_mail import mailbox_address

    base = mailbox_address()
    if "@" not in base:
        return None
    base_local, domain = base.split("@", 1)
    for address in addresses:
        if "@" not in address:
            continue
        local, at_domain = address.rsplit("@", 1)
        if at_domain != domain or not local.startswith(f"{base_local}+nw"):
            continue
        found = KEY_RE.search(local)
        if not found:
            continue
        with rls_bypass():
            link = (
                ProofLink.objects.select_related(
                    "organization", "membership__person", "membership__organization", "discount"
                )
                .filter(mail_key=found.group(1))
                .first()
            )
        if link is not None:
            return link
    return None


def _files(msg: EmailMessage) -> list[tuple[str, str, bytes]]:
    from billing.incoming_import import safe_name

    found = []
    for part in msg.iter_attachments():
        data = part.get_payload(decode=True) or b""
        if not data:
            continue
        name = safe_name(part.get_filename() or "")
        content_type = services.content_type_of(name, part.get_content_type())
        if services.file_problem(name, content_type, data):
            continue
        if not virenscan.inbound_ok(data, name, "Antwort mit Beitragsnachweis"):
            continue
        found.append((name, content_type, data))
        if len(found) >= MAX_ATTACHMENTS:
            break
    return found


def process(msg: EmailMessage, addresses: list[str]) -> str | None:
    """Mail an eine Nachweis-Adresse verarbeiten; None, wenn sie nicht hierher gehört."""
    from billing.incoming_mail import Result, spam_flagged

    link = link_for(addresses)
    if link is None:
        if any("+nw" in a for a in addresses):
            logger.warning("Beitragsnachweis: Mail an unbekannte Antwortadresse bleibt liegen")
            return Result.KEEP
        return None
    if spam_flagged(msg):
        return Result.KEEP
    if link.valid_until < timezone.localdate():
        logger.info("Beitragsnachweis: Antwortadresse abgelaufen, Mail bleibt liegen")
        return Result.KEEP
    org = link.organization
    with tenant_context(org.pk):
        if not services.module_on(org):
            return Result.KEEP
        files = _files(msg)
        subject = re.sub(r"\s+", " ", str(msg.get("Subject", "") or "")).strip()[:200]
        kwargs = {"channel": FeeProof.Channel.MAIL, "check_window": False}
        if not files:
            services.submit(
                link.membership,
                link.discount,
                link.year,
                member_note=f"E-Mail ohne passenden Anhang: {subject}",
                **kwargs,
            )
        for name, content_type, data in files:
            services.submit(
                link.membership,
                link.discount,
                link.year,
                name=name,
                content_type=content_type,
                data=data,
                **kwargs,
            )
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
    return Result.MOVE
