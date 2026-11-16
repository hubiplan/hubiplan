"""Eingebettetes XML aus einer PDF holen (ZUGFeRD/Factur-X).

Läuft für fremde PDFs als eigener Prozess (``python -m finance.pdf_anhang``, PDF über stdin,
XML über stdout) mit Speicher- und Zeitgrenze aus ``finance.einvoice.xml_from_pdf``. Ohne Django.
"""

from __future__ import annotations

import sys

# Gleich finance.einvoice.MAX_XML; größere Anhänge werden gar nicht erst übernommen
MAX_XML = 5 * 1024 * 1024
MAX_ANHAENGE = 50


def xml_aus_pdf(data: bytes) -> bytes | None:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001 - kaputte PDF: einfach keine E-Rechnung
        return None
    try:
        found = None
        for i in range(min(pdf.count_attachments(), MAX_ANHAENGE)):
            attachment = pdf.get_attachment(i)
            name = (attachment.get_name() or "").lower()
            if name.endswith(".xml"):
                content = bytes(attachment.get_data())
                if len(content) > MAX_XML:
                    continue
                if name in ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml"):
                    return content
                found = found or content
        return found
    finally:
        pdf.close()


def main() -> int:
    if len(sys.argv) > 1:
        import resource

        grenze = int(sys.argv[1])
        resource.setrlimit(resource.RLIMIT_AS, (grenze, grenze))
    try:
        content = xml_aus_pdf(sys.stdin.buffer.read())
    except MemoryError:
        return 3
    if content is None:
        return 1
    sys.stdout.buffer.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
