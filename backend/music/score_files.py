"""Notendateien ausliefern: Original, eigene Stimme aus einer MusicXML-Partitur, PDF oder MIDI.

Aus einer Partitur bekommt ein Musiker nur seine Stimme. Lässt sich die Stimme nicht
eindeutig bestimmen, gibt es nichts (statt der ganzen Partitur).
"""

from __future__ import annotations

import os

from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseNotModified
from django.utils.http import content_disposition_header
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from documents import notation
from documents.views import file_response

from .notation_render import check_layout, check_transpose, render

FORMATS = ("", "musicxml", "pdf", "midi")


def kind_of(content_type: str) -> str:
    return {
        notation.MUSICXML: "musicxml",
        notation.MXL: "musicxml",
        notation.MEI: "mei",
        notation.ABC: "abc",
        notation.MIDI: "midi",
    }.get(content_type, "")


def formats_of(content_type: str) -> list[str]:
    if content_type in notation.ENGRAVABLE:
        extra = ["musicxml"] if kind_of(content_type) == "musicxml" else []
        return [*extra, "pdf", "midi"]
    if content_type == notation.MIDI:
        return ["midi"]
    return []


def own_part(link, parts: list[dict]) -> tuple[str | None, bool]:
    """(Stimmen-ID oder None, ganze Datei erlaubt?)."""
    if link.notation_part:
        return notation.find_part(parts, link.notation_part), False
    if len(parts) <= 1:
        return None, True
    if link.part_id and link.part.kind == "part":
        return notation.guess_part(parts, link.part.instrument, link.part.register), False
    # Partitur oder Datei für alle: ganze Datei
    return None, True


def _text(link, version, whole: bool) -> tuple[str, str]:
    """Notentext (bei MusicXML nur die eigene Stimme) und Stimmenname."""
    with version.file.open("rb") as fh:
        raw = fh.read()
    try:
        text = notation.text_of(raw, version.content_type)
        if kind_of(version.content_type) != "musicxml":
            return text, ""
        parts = notation.musicxml_info(text)["parts"]
        part_id, allowed = own_part(link, parts)
    except ValidationError as exc:
        raise NotFound() from exc
    if part_id:
        name = next((p["name"] for p in parts if p["id"] == part_id), "")
        return notation.extract_part(text, part_id), name
    if not (allowed or whole):
        raise NotFound()
    return text, ""


def respond(request, link, version, whole: bool = False):
    """Antwort für ``?format=`` (leer: Original bzw. eigene Stimme), ``?transpose=`` und
    ``?layout=`` (PDF für einen Bildschirm neu umbrochen, siehe ``check_layout``)."""
    fmt = request.query_params.get("format", "")
    transpose = request.query_params.get("transpose", "")
    layout = request.query_params.get("layout", "")
    if fmt not in FORMATS:
        raise serializers.ValidationError({"format": "?"})
    try:
        transpose = check_transpose(transpose)
    except ValidationError as exc:
        raise serializers.ValidationError({"transpose": exc.messages}) from exc
    try:
        layout = check_layout(layout)
    except ValidationError as exc:
        raise serializers.ValidationError({"layout": exc.messages}) from exc
    if layout and fmt != "pdf":
        raise serializers.ValidationError({"layout": "?"})
    ctype = version.content_type
    etag = (
        f'"v{version.pk}{"-" + fmt if fmt else ""}{"-t" + transpose if transpose else ""}'
        f'{"-l" + layout if layout else ""}"'
    )
    if etag in [t.strip() for t in request.headers.get("If-None-Match", "").split(",")]:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response
    stem = os.path.splitext(version.name)[0] or "noten"
    if ctype not in notation.ENGRAVABLE:
        if fmt not in ("", "midi") or (fmt == "midi" and ctype != notation.MIDI) or transpose:
            raise NotFound()
        response = file_response(request, version)
    else:
        text, part_name = _text(link, version, whole)
        if fmt in ("", "musicxml") and not transpose:
            if kind_of(ctype) == "musicxml":
                data, out_type, name = text.encode("utf-8"), notation.MUSICXML, f"{stem}.musicxml"
            else:
                return _with_etag(file_response(request, version), etag)
        elif fmt in ("pdf", "midi"):
            piece = link.arrangement.piece
            heading = [piece.title, piece.composer, part_name or link.document.title]
            try:
                data = render(text, fmt, transpose, heading, layout)
            except ValidationError as exc:
                raise NotFound() from exc
            if fmt == "pdf":
                out_type, name = "application/pdf", f"{stem}.pdf"
            else:
                out_type, name = notation.MIDI, f"{stem}.mid"
        else:
            raise NotFound()
        response = HttpResponse(data, content_type=out_type)
        response["Content-Disposition"] = content_disposition_header(
            out_type != "application/pdf" or request.query_params.get("download") == "1", name
        )
        response["Cache-Control"] = "private, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
    return _with_etag(response, etag)


def _with_etag(response, etag):
    response["ETag"] = etag
    return response
