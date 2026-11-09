"""Notendateien (MusicXML, MEI, ABC, MIDI) in der Dokumentenablage sicher prüfen und lesen.

Nur reines Python: Das Lesen läuft mit defusedxml (keine Entitäten, kein Nachladen) und
begrenztem Entpacken. Das Setzen und Umwandeln (Verovio) liegt in ``music.notation_render``.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from xml.etree.ElementTree import Element  # nur Typ und Serialisieren, Lesen mit defusedxml

from defusedxml import ElementTree as SafeET
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

MUSICXML = "application/vnd.recordare.musicxml+xml"
MXL = "application/vnd.recordare.musicxml"
MEI = "application/mei+xml"
ABC = "text/vnd.abc"
MIDI = "audio/midi"

# Endung: (Dateiart, Anfangsbytes oder None)
NOTATION_TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    "musicxml": (MUSICXML, None),
    "xml": (MUSICXML, None),
    "mxl": (MXL, (b"PK\x03\x04",)),
    "mei": (MEI, None),
    "abc": (ABC, None),
    "mid": (MIDI, (b"MThd",)),
    "midi": (MIDI, (b"MThd",)),
}
NOTATION_HINT = "MusicXML, MEI, ABC oder MIDI"
# Notensatz (Verovio) möglich; MIDI ist nur Hörbeispiel
ENGRAVABLE = {MUSICXML, MXL, MEI, ABC}

MAX_UNZIPPED = 30 * 1024 * 1024
MAX_ENTRIES = 200


def _invalid(text: str | None = None) -> ValidationError:
    return ValidationError({"file": text or gettext("Die Notendatei lässt sich nicht lesen.")})


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _unzip_mxl(data: bytes) -> bytes:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _invalid() from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED:
            raise _invalid(gettext("Die Notendatei ist entpackt zu groß."))
        names = {i.filename for i in infos}
        root = None
        if "META-INF/container.xml" in names:
            container = SafeET.fromstring(archive.read("META-INF/container.xml"))
            for el in container.iter():
                if _local(el.tag) == "rootfile" and el.get("full-path"):
                    root = posixpath.normpath(el.get("full-path"))
                    break
        if root is None:
            root = next(
                (n for n in sorted(names) if n.endswith((".xml", ".musicxml")) and "/" not in n),
                None,
            )
        if not root or root not in names or root.startswith(("/", "..")):
            raise _invalid()
        return archive.read(root)


def text_of(data: bytes, content_type: str) -> str:
    """Notentext einer Datei (MusicXML, MEI oder ABC), MXL entpackt."""
    if content_type == MXL:
        data = _unzip_mxl(data)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise _invalid() from exc


def parse_xml(text: str) -> Element:
    try:
        # DOCTYPE mit öffentlicher DTD ist in MusicXML üblich; Entitäten bleiben verboten
        return SafeET.fromstring(text.encode("utf-8"), forbid_dtd=False)
    except Exception as exc:  # defusedxml meldet Verstöße mit eigenen Ausnahmen
        raise _invalid() from exc


def check(data: bytes, content_type: str) -> None:
    """Prüft den Inhalt einer Notendatei; wirft ValidationError."""
    if content_type == MIDI:
        if not data.startswith(b"MThd"):
            raise _invalid(gettext("Inhalt und Dateiendung passen nicht zusammen."))
        return
    text = text_of(data, content_type)
    if content_type == ABC:
        if not any(line.startswith("X:") for line in text.splitlines()[:50]):
            raise _invalid(gettext("Das ist keine ABC-Notendatei."))
        return
    root = _local(parse_xml(text).tag)
    if content_type in (MUSICXML, MXL) and root not in ("score-partwise", "score-timewise"):
        raise _invalid(gettext("Das ist keine MusicXML-Datei."))
    if content_type == MEI and root != "mei":
        raise _invalid(gettext("Das ist keine MEI-Datei."))


def check_upload(upload, ext: str) -> str:
    ctype, magic = NOTATION_TYPES[ext]
    data = upload.read()
    upload.seek(0)
    if magic and not data.startswith(magic):
        raise _invalid(gettext("Inhalt und Dateiendung passen nicht zusammen."))
    check(data, ctype)
    return ctype


def _text(el: Element | None) -> str:
    return " ".join((el.text or "").split()) if el is not None else ""


def musicxml_info(text: str) -> dict:
    """Titel, Komponist und Stimmen (``part-list``) einer MusicXML-Datei."""
    root = parse_xml(text)
    title = ""
    composer = ""
    parts = []
    for el in root.iter():
        name = _local(el.tag)
        if name in ("work-title", "movement-title") and not title:
            title = _text(el)
        elif name == "creator" and el.get("type") == "composer" and not composer:
            composer = _text(el)
        elif name == "score-part":
            part_name = next((_text(c) for c in el if _local(c.tag) == "part-name"), "")
            parts.append({"id": el.get("id", ""), "name": part_name})
    return {"title": title, "composer": composer, "parts": parts}


def find_part(parts: list[dict], wanted: str) -> str | None:
    """ID einer Stimme nach ID oder Name (ohne Groß-/Kleinschreibung)."""
    key = " ".join(wanted.split()).casefold()
    if not key:
        return None
    for p in parts:
        if p["id"].casefold() == key or p["name"].casefold() == key:
            return p["id"]
    return None


def guess_part(parts: list[dict], instrument: str, register: str) -> str | None:
    """Stimme zu Instrument und Register raten (z. B. „Tenorhorn 1“)."""
    words = [w.casefold() for w in (instrument, register) if w.strip()]
    if not words:
        return None
    hits = [p["id"] for p in parts if all(w in p["name"].casefold() for w in words)]
    return hits[0] if len(hits) == 1 else None


def extract_part(text: str, part_id: str) -> str:
    """MusicXML nur mit einer Stimme; andere Stimmen gelangen nicht aufs Gerät."""
    root = parse_xml(text)
    found = False
    for parent in list(root.iter()):
        for child in list(parent):
            name = _local(child.tag)
            if name == "score-part":
                if child.get("id") == part_id:
                    found = True
                else:
                    parent.remove(child)
            elif name == "part-group":
                parent.remove(child)
            elif name == "part" and _local(parent.tag) in ("score-partwise", "measure"):
                if child.get("id") != part_id:
                    parent.remove(child)
    if not found:
        raise _invalid(gettext("Diese Stimme gibt es in der Notendatei nicht."))
    from xml.etree.ElementTree import tostring

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode")
