"""Eine eingehende E-Rechnung in den Rechnungseingang übernehmen.

Gemeinsamer Weg für das Hochladen (einvoice_views.py) und das Rechnungspostfach
(incoming_mail.py): Original speichern, XML auslesen, Dublettenschutz je Verein über den
SHA-256 der Datei, KoSIT-Prüfung im Hintergrund (incoming_check.py).
"""

from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.db import connection
from django.utils.translation import gettext

from audit.log import record
from finance import einvoice
from finance.services import lock_bank_sources

from . import einvoice_validator, incoming_check
from .models import IncomingInvoice

# Größte Datei, die das Hochladen und das Postfach annehmen
MAX_BYTES = 15 * 1024 * 1024


def safe_name(name: str) -> str:
    return (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()[:200] or "rechnung"


def store(org, raw: bytes, name: str, user=None, mail=None) -> tuple[IncomingInvoice, bool]:
    """Datei übernehmen. Gibt den Eingang zurück und ob er neu angelegt wurde.

    Nur innerhalb einer Transaktion im Kontext des Vereins aufrufen.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("Eingang nur innerhalb einer Transaktion übernehmen.")
    digest = hashlib.sha256(raw).hexdigest()
    # Gleichzeitige Wiederholungen serialisieren, ohne externe Daten als Sperrschlüssel.
    lock_bank_sources(org)
    existing = IncomingInvoice.objects.filter(organization=org, sha256=digest).first()
    if existing:
        return existing, False
    content_type = "application/pdf" if raw.startswith(b"%PDF") else "application/xml"
    data, xml = {}, b""
    report, report_xml = einvoice_validator.failed(
        gettext("Keine unterstützte E-Rechnung erkannt.")
    )
    try:
        xml = einvoice.xml_from_pdf(raw) if content_type == "application/pdf" else raw
        if xml:
            data = einvoice.as_json(einvoice.parse_xml(xml))
            report, report_xml = incoming_check.pending_report(), b""
    except (einvoice.EInvoiceError, ValueError, RuntimeError) as exc:
        report, report_xml = einvoice_validator.failed(str(exc))
    pending = report["status"] == "pending"
    item = IncomingInvoice.objects.create(
        organization=org,
        name=safe_name(name),
        sha256=digest,
        content_type=content_type,
        data=data,
        report=report,
        validation="pending" if pending else "done",
        created_by=user if user is not None and user.is_authenticated else None,
        mail=mail,
    )
    item.original.save(
        "original.pdf" if content_type == "application/pdf" else "original.xml",
        ContentFile(raw),
        save=False,
    )
    if xml:
        item.xml.save("invoice.xml", ContentFile(xml), save=False)
    if report_xml:
        item.report_xml.save("validation.xml", ContentFile(report_xml), save=False)
    item.save()
    changes = {"Rechnungseingang": [None, item.name]}
    if mail is not None:
        changes["Per Mail von"] = [None, mail.sender]
    record(org, user, "create", item, changes)
    if pending:
        incoming_check.schedule(org.pk)
    return item, True
