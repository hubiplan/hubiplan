"""Noten setzen mit Verovio (LGPL-3.0): PDF für Browser, Druck und Gäste, MIDI zum Anhören.

Verovio ist eine native Bibliothek. Damit eine kaputte oder riesige Datei keinen
Webprozess mitreißt, läuft das Setzen in einem eigenen Prozess mit Zeitgrenze. Ergebnisse
liegen eine Woche im Cache (je Fassung, Stimme, Ausgabe und Transposition).
"""

from __future__ import annotations

import hashlib
import io
import logging
import multiprocessing
import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

log = logging.getLogger(__name__)

TIMEOUT = 60
CACHE_SECONDS = 7 * 24 * 3600
MAX_PAGES = 200
# Intervall wie bei Verovio („M2“, „-m3“, „P8“) oder Halbtöne („-3“, „+2“)
TRANSPOSE = re.compile(
    r"^(?:[+-]?(?:[1-9]|1[0-2])|-?(?:P1|m2|M2|m3|M3|P4|A4|d5|P5|m6|M6|m7|M7|P8))$"
)


# Satz für einen Bildschirm (App): „<Höhe je 1000 Breite>x<Notengröße>“, z. B. „1778x55“
LAYOUT = re.compile(r"^(\d{3,4})x(\d{2,3})$")
A4_WIDTH_PT = 595.2756


def check_layout(value: str) -> str:
    """Seitenverhältnis 0,8–3 und Notengröße 25–120 (Verovio-Skala); leer: A4 wie im Browser."""
    value = (value or "").strip()
    if not value:
        return ""
    match = LAYOUT.match(value)
    if not match or not (800 <= int(match.group(1)) <= 3000 and 25 <= int(match.group(2)) <= 120):
        raise ValidationError(gettext("Dieses Seitenformat ist nicht möglich."))
    return value


def check_transpose(value: str) -> str:
    value = (value or "").strip()
    if value and not TRANSPOSE.match(value):
        raise ValidationError(gettext("Diese Transposition ist nicht möglich."))
    return value


def _work(conn, text: str, out: str, transpose: str, heading: list[str], layout: str) -> None:
    try:
        conn.send(("ok", _render(text, out, transpose, heading, layout)))
    except Exception:  # noqa: BLE001 – Ergebnis an den Elternprozess, nie Absturz dort
        import traceback

        conn.send(("error", traceback.format_exc(limit=8)[-2000:]))
    finally:
        conn.close()


def _render(text: str, out: str, transpose: str, heading: list[str], layout: str = "") -> bytes:
    import base64

    import verovio

    tk = verovio.toolkit()
    options = {
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 450 if heading else 60,
        "scale": 45,
        "header": "none",
        "footer": "none",
        "adjustPageHeight": False,
        "breaks": "auto",
    }
    page_size = None
    if layout:
        # Für den Bildschirm neu umbrechen: Seite im Verhältnis des Geräts, schmale Ränder
        ratio, scale = (int(v) for v in LAYOUT.match(layout).groups())
        options.update(
            pageHeight=2100 * ratio // 1000,
            scale=scale,
            pageMarginLeft=40,
            pageMarginRight=40,
            pageMarginBottom=40,
            pageMarginTop=300 if heading else 40,
        )
        page_size = (A4_WIDTH_PT, A4_WIDTH_PT * ratio / 1000)
    if transpose:
        options["transpose"] = transpose
    tk.setOptions(options)
    if not text.strip() or not tk.loadData(text):
        raise ValueError("unlesbar")
    if out == "midi":
        return base64.b64decode(tk.renderToMIDI())
    pages = tk.getPageCount()
    if pages < 1 or pages > MAX_PAGES:
        raise ValueError("Seitenzahl")
    from reportlab.graphics import renderPDF
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from svglib.svglib import svg2rlg

    buf = io.BytesIO()
    size = page_size or A4
    pdf = canvas.Canvas(buf, pagesize=size)
    width, height = size
    for page in range(1, pages + 1):
        drawing = svg2rlg(io.StringIO(tk.renderToSVG(page)))
        if drawing is None:
            raise ValueError("SVG")
        factor = min(width / drawing.width, height / drawing.height)
        drawing.scale(factor, factor)
        renderPDF.draw(drawing, pdf, 0, height - drawing.height * factor)
        if page == 1 and heading:
            # Nur PDF-Standardschriften, keine eingebettete Schriftdatei (docs/lizenzen.md)
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawCentredString(width / 2, height - 36, heading[0][:120])
            pdf.setFont("Helvetica", 10)
            for n, line in enumerate(heading[1:3], start=1):
                pdf.drawCentredString(width / 2, height - 36 - 14 * n, line[:160])
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def render(
    text: str,
    out: str,
    transpose: str = "",
    heading: list[str] | None = None,
    layout: str = "",
) -> bytes:
    """``out``: ``pdf`` oder ``midi``; ``layout`` siehe :func:`check_layout` (nur PDF).

    Wirft ValidationError, wenn Setzen nicht gelingt.
    """
    transpose = check_transpose(transpose)
    layout = check_layout(layout) if out == "pdf" else ""
    heading = [h for h in (heading or []) if h]
    key = (
        "noten:"
        + hashlib.sha256("\x00".join([out, transpose, layout, *heading, text]).encode()).hexdigest()
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_work, args=(child, text, out, transpose, heading, layout), daemon=True
    )
    proc.start()
    child.close()
    result = None
    if parent.poll(TIMEOUT):
        try:
            result = parent.recv()
        except EOFError:
            result = None
    proc.join(1)
    if proc.is_alive():
        proc.kill()
        proc.join()
    parent.close()
    if not result or result[0] != "ok":
        log.warning(
            "Noten setzen (%s) fehlgeschlagen: %s, Exitcode %s",
            out,
            result[1] if result else "keine Antwort",
            proc.exitcode,
        )
        raise ValidationError(gettext("Die Noten ließen sich nicht setzen."))
    cache.set(key, result[1], CACHE_SECONDS)
    return result[1]
