"""Dokumente der Webseite (Ralf 05.11., Kapelle): Pressespiegel und weitere Dateien.

Erlaubt sind PDF und Bilder (JPEG, PNG, WebP). Bilder werden wie alle Bilder der
Webseite neu geschrieben (ohne EXIF/GPS); PDFs bleiben, wie sie sind, und bekommen ein
Vorschaubild der ersten Seite.
"""

from __future__ import annotations

import io
import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from . import content
from .content_models import WebsiteDocument

log = logging.getLogger(__name__)

MAX_PDF_BYTES = 20 * 1024 * 1024
PREVIEW_WIDTH = 480
PREVIEW_MAX_HEIGHT = 1200


def _pdf_preview(data: bytes) -> bytes | None:
    """JPEG der ersten Seite oder None, wenn sich die Datei nicht lesen lässt."""
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            page = pdf[0]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                return None
            scale = min(PREVIEW_WIDTH / width, PREVIEW_MAX_HEIGHT / height)
            image = page.render(scale=scale).to_pil()
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
            return out.getvalue()
        finally:
            pdf.close()
    except Exception:  # noqa: BLE001 - kaputte PDF: ohne Vorschau
        log.warning("Vorschau für ein Dokument der Webseite nicht möglich", exc_info=True)
        return None


def _is_pdf(upload) -> bool:
    upload.seek(0)
    head = upload.read(5)
    upload.seek(0)
    return head == b"%PDF-"


def store(website, upload, *, section: str, title: str, source: str, date, user):
    doc = WebsiteDocument(
        organization=website.organization,
        website=website,
        key=WebsiteDocument.new_key(),
        section=section,
        title=title,
        source=source,
        date=date,
        file_name=(getattr(upload, "name", "") or "")[:200],
        uploaded_by=user,
    )
    if _is_pdf(upload):
        if upload.size > MAX_PDF_BYTES:
            raise ValidationError(
                {"file": gettext("Die PDF-Datei darf höchstens 20 MB groß sein.")}
            )
        data = upload.read()
        doc.content_type = "application/pdf"
        doc.size = len(data)
        doc.file.save("dokument.pdf", ContentFile(data), save=False)
        preview = _pdf_preview(data)
        if preview:
            doc.preview.save("vorschau.jpg", ContentFile(preview), save=False)
    else:
        try:
            full, ext, _w, _h, small, ext_small = content.process_image(upload)
        except ValidationError as exc:
            raise ValidationError(
                {
                    "file": gettext(
                        "Bitte eine PDF-Datei oder ein JPEG-, PNG- oder WebP-Bild hochladen."
                    )
                }
            ) from exc
        doc.content_type = "image/png" if ext == "png" else "image/jpeg"
        doc.size = len(full)
        doc.file.save(f"dokument.{ext}", ContentFile(full), save=False)
        doc.preview.save(f"vorschau.{ext_small}", ContentFile(small), save=False)
    doc.save()
    return doc


def delete(doc: WebsiteDocument) -> None:
    names = [f.name for f in (doc.file, doc.preview) if f.name]
    storage = doc.file.storage
    doc.delete()

    def _remove():
        for name in names:
            storage.delete(name)

    transaction.on_commit(_remove)


def public_list(site, section: str) -> list[dict]:
    rows = WebsiteDocument.objects.filter(website=site.site, section=section, published=True)
    return [
        {
            "id": d.key,
            "title": d.title,
            "source": d.source,
            "date": d.date.isoformat() if d.date else None,
            "kind": "pdf" if d.content_type == "application/pdf" else "image",
            "url": site.url(f"files/{d.key}/"),
            "preview_url": site.url(f"files/{d.key}/?size=small") if d.preview.name else None,
            "size": d.size,
        }
        for d in rows
    ]


def find(site, key: str) -> WebsiteDocument | None:
    doc = WebsiteDocument.objects.filter(website=site.site, key=key, published=True).first()
    if doc is None:
        return None
    block = "press" if doc.section == WebsiteDocument.Section.PRESS else "statutes"
    return doc if site.site.block_on(block) else None
