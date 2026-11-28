"""Belege an Buchungen: Datei prüfen und anhängen, Löschfrist, Quittung zur Buchung (ohne HTTP)."""

from __future__ import annotations

import datetime
import mimetypes

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from audit.log import record
from core import filecheck

from . import services
from .models import (
    Booking,
    Receipt,
)

MAX_RECEIPT_BYTES = 15 * 1024 * 1024


RECEIPT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    # E-Rechnungen (XRechnung, reines XML)
    "application/xml",
    "text/xml",
}


QUITTUNG_LOCKED = (
    "Die Buchung gehört zu einer unterschriebenen Quittung und lässt sich nicht ändern oder "
    "löschen. Bitte die Quittung stornieren."
)


def _quittung_of(booking: Booking):
    """Quittung, zu der die Buchung gehört (Abschluss oder Storno), sonst None."""
    from .models import CashReceipt

    return CashReceipt.objects.filter(Q(booking=booking) | Q(cancel_booking=booking)).first()


def attach_receipt(org, booking: Booking, upload, user) -> Receipt:
    """Beleg prüfen, speichern und protokollieren (Browser und App)."""
    if upload is None:
        raise serializers.ValidationError({"file": gettext("Bitte eine Datei wählen.")})
    if upload.size > MAX_RECEIPT_BYTES:
        raise serializers.ValidationError({"file": gettext("Die Datei ist größer als 15 MB.")})
    content_type = (upload.content_type or mimetypes.guess_type(upload.name)[0] or "").lower()
    if content_type not in RECEIPT_TYPES:
        raise serializers.ValidationError(
            {
                "file": gettext(
                    "Erlaubt sind PDF, Fotos (JPEG, PNG, WebP, HEIC) und E-Rechnungen (XML)."
                )
            }
        )
    head = upload.read(16)
    upload.seek(0)
    if content_type == "application/pdf" and not head.startswith(b"%PDF"):
        raise serializers.ValidationError({"file": gettext("Die Datei ist kein PDF.")})
    if content_type.startswith("image/") and not filecheck.is_image(head):
        # Nicht nur der Angabe des Geräts trauen
        raise serializers.ValidationError({"file": filecheck.image_message()})
    info: dict = {}
    if content_type in ("application/pdf", "application/xml", "text/xml"):
        from . import einvoice

        data = upload.read()
        upload.seek(0)
        try:
            found = einvoice.read(data, content_type)
        except einvoice.EInvoiceError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from exc
        if found:
            info = einvoice.as_json(found)
        if content_type != "application/pdf":
            content_type = "application/xml"
    name = upload.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200]
    receipt = Receipt(
        organization=org,
        booking=booking,
        name=name,
        content_type=content_type,
        size=upload.size,
        uploaded_by=user,
        einvoice=info,
    )
    receipt.file.save(_safe_name(name), upload, save=False)
    receipt.save()
    record(
        org,
        user,
        "create",
        receipt,
        {"Beleg": [None, f"{name} zu Buchung {booking.display_number}"]},
    )
    return receipt


# Versehentlich hochgeladene Datei: nur kurz danach und nur von derselben Person löschbar
RECEIPT_DELETE_MINUTES = 15


def receipt_deletable(receipt: Receipt, user) -> bool:
    if receipt.uploaded_by_id is None or receipt.uploaded_by_id != getattr(user, "pk", None):
        return False
    if timezone.now() - receipt.created_at > datetime.timedelta(minutes=RECEIPT_DELETE_MINUTES):
        return False
    return not services.fixed_reason(receipt.booking)


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)
    return keep[-80:] or "beleg"
