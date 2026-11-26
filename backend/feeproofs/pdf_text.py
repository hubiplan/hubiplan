"""Text der ersten Seiten einer PDF lesen (Vorprüfung der Beitragsnachweise).

Läuft für eingereichte PDFs als eigener Prozess (``python -m feeproofs.pdf_text``, PDF über
stdin, Text über stdout) mit Speicher- und Zeitgrenze aus ``feeproofs.precheck.pdf_text``:
Eine präparierte Datei beendet so höchstens diesen Prozess, nie den Web- oder Mailabruf-Prozess.
Ohne Django.
"""

from __future__ import annotations

import sys

MAX_CHARS = 200_000


def text_aus_pdf(data: bytes, max_pages: int) -> str:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001 - kaputtes oder verschlüsseltes PDF: kein Text
        return ""
    try:
        parts: list[str] = []
        total = 0
        for i in range(min(len(doc), max_pages)):
            try:
                page = doc[i]
                textpage = page.get_textpage()
                chunk = textpage.get_text_range()
                textpage.close()
                page.close()
            except Exception:  # noqa: BLE001, S112 - beschädigte Seite: Text der übrigen Seiten
                continue
            parts.append(chunk[: MAX_CHARS - total])
            total += len(parts[-1])
            if total >= MAX_CHARS:
                break
        return "\n".join(parts)
    finally:
        doc.close()


def main() -> int:
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    if len(sys.argv) > 2:
        import resource

        grenze = int(sys.argv[2])
        resource.setrlimit(resource.RLIMIT_AS, (grenze, grenze))
    try:
        text = text_aus_pdf(sys.stdin.buffer.read(), max_pages)
    except MemoryError:
        return 3
    sys.stdout.buffer.write(text.encode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
