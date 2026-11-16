"""Ausgegebene Rechnungen als PDF ablegen (Fachfrage 4, Audit 31.10.).

Eine festgeschriebene Rechnung wird beim ersten Versand bzw. Abruf einmal erzeugt und
gespeichert; danach gilt immer diese Fassung, auch wenn sich Briefkopf, Bankverbindung
oder Vorlage ändern. Entwürfe und stornierte Rechnungen werden weiter frisch erzeugt.
"""

from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from . import pdf
from .models import Invoice

ARCHIVED = (Invoice.Status.OPEN, Invoice.Status.PAID, Invoice.Status.SETTLED)


def _purged_years():
    """Jahre, deren Belege nach Ablauf der Aufbewahrungsfrist gelöscht sind."""
    from finance.models import YearClosing

    return YearClosing.objects.filter(
        organization_id=OuterRef("organization_id"),
        year=OuterRef("year"),
        documents_purged_at__isnull=False,
    )


def documents_purged(invoice: Invoice) -> bool:
    """Ist das PDF dieser Rechnung nach Fristablauf gelöscht? Dann wird es nicht neu
    erzeugt (Audit 02.11. BP-V03)."""
    from finance.models import YearClosing

    return (
        invoice.year is not None
        and YearClosing.objects.filter(
            organization_id=invoice.organization_id,
            year=invoice.year,
            documents_purged_at__isnull=False,
        ).exists()
    )


def archived_pdf(invoice: Invoice) -> bytes:
    """PDF der Rechnung in der ausgegebenen Fassung (legt sie beim ersten Mal ab)."""
    if invoice.electronic_data and invoice.issued_pdf:
        with invoice.issued_pdf.open("rb") as fh:
            return fh.read()
    if invoice.electronic_data and invoice.status == Invoice.Status.DRAFT:
        from finance.einvoice import parse_xml, render

        from .einvoice_xml import generate

        return render(parse_xml(generate(invoice)), invoice.organization.display_name)
    if invoice.status == Invoice.Status.CANCELLED and invoice.issued_pdf:
        # Storniert: die Rechnung bleibt, wie sie ausgegeben wurde; das Storno steht auf der
        # eigenen Stornorechnung (archived_cancellation)
        with invoice.issued_pdf.open("rb") as fh:
            return fh.read()
    if invoice.status not in ARCHIVED or invoice.number is None:
        return pdf.render([invoice])
    if invoice.issued_pdf:
        with invoice.issued_pdf.open("rb") as fh:
            return fh.read()
    if documents_purged(invoice):
        raise ValidationError(
            gettext(
                "Die Aufbewahrungsfrist dieser Rechnung ist abgelaufen; ihr PDF wurde gelöscht."
            )
        )
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.issued_pdf:
            with locked.issued_pdf.open("rb") as fh:
                return fh.read()
        content = pdf.render([locked])
        locked.issued_pdf_sha256 = hashlib.sha256(content).hexdigest()
        locked.issued_pdf.save(pdf.filename(locked), ContentFile(content), save=False)
        locked.save(update_fields=["issued_pdf", "issued_pdf_sha256", "updated_at"])
    invoice.issued_pdf = locked.issued_pdf
    invoice.issued_pdf_sha256 = locked.issued_pdf_sha256
    return content


def archived_cancellation(invoice: Invoice) -> bytes | None:
    """Die abgelegte Stornorechnung; None bei Stornos aus der Zeit vor der Stornorechnung."""
    if not invoice.cancellation_pdf:
        return None
    with invoice.cancellation_pdf.open("rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != invoice.cancellation_pdf_sha256:
        raise ValidationError(gettext("Die Prüfsumme der Stornorechnung stimmt nicht."))
    return data


# Rechnungen, deren Ablage scheiterte, ruhen so lange; dann neuer Versuch (Gesamtaudit 15.11.,
# PF-10). Vorher stand eine scheiternde Rechnung immer vorn, und keine weitere wurde je abgelegt.
FAILED_PAUSE = 24 * 60 * 60
FAILED_KEY = "rechnungen-ablage-fehlerhaft"


def archive_missing(limit: int = 200) -> int:
    """Noch nicht abgelegte festgeschriebene Rechnungen nachträglich ablegen
    (z. B. Postversand über den Sammel-PDF eines Beitragslaufs).

    Jede Rechnung für sich: Scheitert eine, ruht sie einen Tag, die übrigen werden abgelegt;
    eine Alarm-Mail nennt die gescheiterten (höchstens einmal am Tag je Stand)."""
    import logging

    from django.core.cache import cache

    from core.tenancy import rls_bypass

    logger = logging.getLogger(__name__)
    paused = set(cache.get(FAILED_KEY) or [])
    failed: list[int] = []
    done = 0
    with rls_bypass():
        ids = list(
            Invoice.objects.filter(status__in=ARCHIVED, number__isnull=False, issued_pdf="")
            .exclude(Exists(_purged_years()))
            .exclude(pk__in=paused)
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in ids:
            try:
                invoice = Invoice.objects.select_related("organization").get(pk=pk)
                archived_pdf(invoice)
            except Exception:  # noqa: BLE001 – eine Rechnung darf die übrigen nicht aufhalten
                logger.exception("Rechnung %s ließ sich nicht ablegen", pk)
                failed.append(pk)
                continue
            done += 1
    if failed:
        cache.set(FAILED_KEY, sorted(paused | set(failed)), FAILED_PAUSE)
        _alert_failed(failed)
    return done


def _alert_failed(pks: list[int]) -> None:
    import hashlib

    from django.core.cache import cache

    from core.alarm import send_alert

    key = hashlib.sha256(str(sorted(pks)).encode()).hexdigest()[:32]
    if cache.add(f"rechnungen-ablage-alarm:{key}", 1, 24 * 60 * 60):
        send_alert(
            "Rechnungen ließen sich nicht ablegen",
            [
                f"{len(pks)} festgeschriebene Rechnungen ließen sich nicht als PDF ablegen "
                f"(Kennungen: {', '.join(str(pk) for pk in pks[:20])}).",
                "Die übrigen wurden abgelegt; diese werden in 24 Stunden erneut versucht.",
                "Einzelheiten im Protokoll des Workers.",
            ],
        )


def archived_dunning(dunning) -> bytes:
    """Mahnfassung einmal ablegen; spätere Zahlungen verändern sie nicht."""
    from finance.models import YearClosing

    from .models import Dunning

    with transaction.atomic():
        locked = Dunning.objects.select_for_update().get(pk=dunning.pk)
        if locked.issued_pdf:
            with locked.issued_pdf.open("rb") as fh:
                return fh.read()
        year = locked.organization.fiscal_year_of(locked.date)
        if YearClosing.objects.filter(
            organization=locked.organization, year=year, documents_purged_at__isnull=False
        ).exists():
            raise ValidationError(gettext("Die Aufbewahrungsfrist ist abgelaufen."))
        content = pdf.render([locked.invoice], {locked.invoice_id: locked})
        locked.issued_pdf_sha256 = hashlib.sha256(content).hexdigest()
        locked.issued_pdf.save(pdf.dunning_filename(locked), ContentFile(content), save=False)
        locked.save(update_fields=["issued_pdf", "issued_pdf_sha256"])
        return content
