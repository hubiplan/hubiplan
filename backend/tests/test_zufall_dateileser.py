"""Zufallstests für alles, was fremde Dateien liest (Härtung C3).

Jeder Leser bekommt gültige Vorlagen, die zufällig verdreht werden (abgeschnitten, Bytes
gekippt, Stücke vervielfacht, typische Störwerte eingesetzt), dazu reinen Zufall. Verlangt
wird: Der Leser liest sauber oder lehnt mit seiner eigenen, verständlichen Ausnahme ab. Jede
andere Ausnahme (KeyError, IndexError, RecursionError, …) wäre im Betrieb ein Fehler 500 und
gilt hier als Fund. Dazu darf kein einzelner Aufruf lange rechnen.

Im normalen Testlauf sind die Beispiele fest (``derandomize``), damit ein Lauf wiederholbar
ist und kein fremder Pull Request an einem Zufallsfund hängen bleibt. Wer sucht, setzt
``HUBIPLAN_ZUFALL=<Anzahl>``: dann echte Zufallsbeispiele in dieser Zahl je Leser.

Ein neuer Leser für fremde Dateien bekommt hier einen Eintrag in ``LESER``.
"""

import io
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rest_framework.exceptions import ValidationError as DrfValidationError

from core import filecheck
from documents import notation
from events import external, imip
from exchange import reading
from feeproofs import precheck
from finance import camt, einvoice
from members import photos
from website import design_packages

from .test_fremde_kalender import ICS
from .test_kontoauszug import camt_xml

SUCHE = int(os.environ.get("HUBIPLAN_ZUFALL", "0") or 0)
BEISPIELE = SUCHE or 60
# Großzügig, weil der Testlauf die Kerne teilt; ein hängender Leser braucht ein Vielfaches
HOECHSTDAUER = 20.0

EINSTELLUNG = settings(
    max_examples=BEISPIELE,
    derandomize=not SUCHE,
    database=None,
    deadline=None,
    suppress_health_check=list(HealthCheck),
)

DATEN = Path(__file__).parent / "data"

STOERWERTE = [
    b"",
    b"\x00",
    b"\xff\xfe",
    b"\xef\xbb\xbf",
    b"<!DOCTYPE x [<!ENTITY a 'b'>]>",
    b"&a;",
    b"<" * 40,
    b"]]>",
    b"9" * 400,
    b"-1",
    b"1e999",
    b"NaN",
    b"\r\n ",
    b"BEGIN:VEVENT\r\n",
    b"END:VEVENT\r\n",
    b"RRULE:FREQ=SECONDLY;INTERVAL=1\r\n",
    b"RRULE:FREQ=YEARLY;COUNT=999999999\r\n",
    b"DTSTART:00000101T000000Z\r\n",
    b"DTSTART:99991231T235959Z\r\n",
    b"DURATION:P999999999W\r\n",
    b"PK\x03\x04",
    b"%PDF-1.7\n",
    b"/ByteRange [0 99999999 99999999 99999999]",
    b"/ByteRange [0 0 0 0]",
    b";" * 50,
    b'"',
    "ä€𝄞".encode(),
    "‮".encode(),
]


def _verdrehen(vorlage: bytes, schritte: list[tuple[int, int, int, int]]) -> bytes:
    data = bytearray(vorlage)
    for art, a, b, c in schritte:
        n = len(data)
        pos = a % (n + 1)
        ende = min(n, pos + b % 64)
        if art == 0:  # abschneiden
            del data[pos:]
        elif art == 1 and n:  # Byte kippen
            data[pos % n] ^= 1 << (c % 8)
        elif art == 2:  # Stück löschen
            del data[pos:ende]
        elif art == 3:  # Stück vervielfachen
            data[pos:pos] = bytes(data[pos:ende]) * (1 + c % 20)
        elif art == 4:  # Störwert einsetzen
            data[pos:pos] = STOERWERTE[c % len(STOERWERTE)]
        elif art == 5:  # Störwert überschreibt
            wert = STOERWERTE[c % len(STOERWERTE)]
            data[pos : pos + len(wert)] = wert
        elif art == 6 and n:  # zwei Stücke tauschen
            q = c % n
            data[pos:ende], data[q : q + (ende - pos)] = (
                bytes(data[q : q + (ende - pos)]),
                bytes(data[pos:ende]),
            )
    return bytes(data)


SCHRITTE = st.lists(
    st.tuples(
        st.integers(0, 6),
        st.integers(0, 1 << 20),
        st.integers(0, 1 << 10),
        st.integers(0, 1 << 20),
    ),
    max_size=6,
)


def eingaben(vorlagen: list[bytes]):
    """Verdrehte Vorlagen, dazu reiner Zufall."""
    verdreht = st.builds(_verdrehen, st.sampled_from(vorlagen), SCHRITTE)
    return st.one_of(verdreht, verdreht, verdreht, st.binary(max_size=600))


# --- Vorlagen: klein, gültig, erfunden ---------------------------------------------------


def _zip(dateien: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, inhalt in dateien.items():
            archive.writestr(name, inhalt)
    return buf.getvalue()


def _bild(fmt: str) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (24, 16), (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


def _xlsx() -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["Vorname", "Nachname", "Eintritt"])
    sheet.append(["Erika", "Musterfrau", "2020-01-01"])
    sheet.append(["Max", "Mustermann", 12])
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def _pdf() -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    seite = canvas.Canvas(buf)
    seite.drawString(72, 720, "Immatrikulationsbescheinigung gültig bis 31.03.2027")
    seite.save()
    return buf.getvalue()


BUCHUNG = """<Ntry><Amt Ccy="EUR">12.50</Amt><CdtDbtInd>CRDT</CdtDbtInd>
  <BookgDt><Dt>2025-03-05</Dt></BookgDt><ValDt><Dt>2025-03-05</Dt></ValDt>
  <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Erika Musterfrau</Nm></Dbtr>
  <DbtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></DbtrAcct></RltdPties>
  <RmtInf><Ustrd>Beitrag 2025 RE-2025-0001</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""
CAMT = camt_xml([BUCHUNG], closing="12.50")
CAMT_ZIP = _zip({"auszug.xml": CAMT})
ERECHNUNG = (DATEN / "einvoice-en16931.xml").read_bytes()
KALENDER = ICS.format(
    d1="20270105", d2="20270107", d2b="20270108", d3="20270114", d3b="20270115", d4="20270121"
).encode()
EINLADUNG = (
    b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\n"
    b"UID:einladung@example.org\r\nSEQUENCE:1\r\nDTSTART:20270105T180000Z\r\n"
    b"DTEND:20270105T200000Z\r\nSUMMARY:Vorstandssitzung\r\n"
    b"ORGANIZER;CN=Erika Musterfrau:mailto:erika@example.org\r\n"
    b"ATTENDEE;CN=Max Mustermann;RSVP=TRUE:mailto:max@example.org\r\n"
    b"LOCATION:Vereinsheim\r\nDESCRIPTION:https://meet.example.org/raum\r\n"
    b"END:VEVENT\r\nEND:VCALENDAR\r\n"
)
CSV = b"Vorname;Nachname;Eintritt\r\nErika;Musterfrau;01.01.2020\r\nMax;Mustermann;\r\n"
XLSX = _xlsx()
MUSICXML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n<score-partwise version="4.0"><part-list>'
    b'<score-part id="P1"><part-name>Trompete</part-name></score-part></part-list>'
    b'<part id="P1"><measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch>'
    b"<duration>2</duration><type>half</type></note></measure></part></score-partwise>"
)
MXL = _zip(
    {
        "META-INF/container.xml": (
            '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>'
        ),
        "score.xml": MUSICXML,
    }
)
MEI = b'<?xml version="1.0"?><mei xmlns="http://www.music-encoding.org/ns/mei"><music/></mei>'
ABC = b"X:1\nT:Marsch\nM:4/4\nK:C\nCDEF|GABc|\n"
MIDI = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
DESIGN = design_packages.build_zip(
    key="erfunden",
    label="Erfunden",
    label_en="Invented",
    hint="Ein Design zum Prüfen",
    hint_en="A design for testing",
    roles={"header": [0]},
    sketch_like="classic",
    css=":root { --farbe: #123456; }\n.kopf { color: var(--farbe); }\n",
    templates={},
    exported="2026-11-22",
)
PNG, JPEG, WEBP = _bild("PNG"), _bild("JPEG"), _bild("WEBP")
PDF = _pdf()


# --- Leser: Aufruf und die Ausnahmen, mit denen er ablehnen darf --------------------------


def _tabelle(endung: str):
    def lesen(data: bytes):
        with tempfile.NamedTemporaryFile(suffix=endung) as datei:
            datei.write(data)
            datei.flush()
            return reading.read_table(datei.name, f"import{endung}")

    return lesen


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _noten(art: str):
    return lambda data: notation.check(data, art)


def _noten_stimmen(data: bytes):
    text = notation.text_of(data, notation.MUSICXML)
    info = notation.musicxml_info(text)
    for teil in info.get("parts", [])[:3]:
        notation.extract_part(text, teil.get("id", ""))
    return info


NOTENFEHLER = (DjangoValidationError, DrfValidationError)
BILDFEHLER = (DjangoValidationError, DrfValidationError)

LESER = [
    ("kontoauszug", camt.parse, (camt.CamtError,), [CAMT, CAMT_ZIP]),
    ("kontoauszug_abruf", camt.parse_fetched, (camt.CamtError,), [CAMT]),
    ("e_rechnung_xml", einvoice.parse_xml, (einvoice.EInvoiceError,), [ERECHNUNG]),
    (
        "e_rechnung_pdf",
        lambda data: einvoice.read(data, "application/pdf"),
        (einvoice.EInvoiceError,),
        [PDF, ERECHNUNG],
    ),
    (
        "kalender",
        lambda data: external.parse_ical(_text(data)),
        (external.ExternalError,),
        [KALENDER, EINLADUNG],
    ),
    (
        "einladung",
        lambda data: imip.read(_text(data)),
        (imip.NotUsable,),
        [EINLADUNG, KALENDER],
    ),
    ("tabelle_csv", _tabelle(".csv"), (reading.ReadError,), [CSV]),
    ("tabelle_xlsx", _tabelle(".xlsx"), (reading.ReadError,), [XLSX]),
    ("noten_musicxml", _noten(notation.MUSICXML), NOTENFEHLER, [MUSICXML]),
    ("noten_mxl", _noten(notation.MXL), NOTENFEHLER, [MXL]),
    ("noten_mei", _noten(notation.MEI), NOTENFEHLER, [MEI]),
    ("noten_abc", _noten(notation.ABC), NOTENFEHLER, [ABC]),
    ("noten_midi", _noten(notation.MIDI), NOTENFEHLER, [MIDI]),
    ("noten_stimmen", _noten_stimmen, NOTENFEHLER, [MUSICXML]),
    ("designpaket", design_packages.read, (design_packages.PackageError,), [DESIGN]),
    ("dateiart", filecheck.sniff, (), [PNG, JPEG, WEBP, PDF]),
    ("logo", filecheck.clean_logo, BILDFEHLER, [PNG, JPEG, WEBP]),
    ("mitgliederfoto", photos.clean_photo, BILDFEHLER, [PNG, JPEG, WEBP]),
    ("nachweis_text", precheck.pdf_text, (), [PDF]),
    ("nachweis_signatur", precheck.signature_info, (), [PDF]),
]


@pytest.mark.parametrize("name", [eintrag[0] for eintrag in LESER])
def test_leser_liest_oder_lehnt_sauber_ab(name):
    _, lesen, ablehnung, vorlagen = next(e for e in LESER if e[0] == name)

    @EINSTELLUNG
    @given(eingaben(vorlagen))
    def lauf(data):
        beginn = time.monotonic()
        try:
            lesen(data)
        except ablehnung:
            pass
        dauer = time.monotonic() - beginn
        assert dauer < HOECHSTDAUER, f"{name}: {dauer:.1f} s für {len(data)} Bytes"

    lauf()


@pytest.mark.parametrize("name", [eintrag[0] for eintrag in LESER])
def test_vorlagen_sind_gueltig(name):
    """Die unverdrehte Vorlage wird gelesen; sonst prüfte der Zufallstest nur die Ablehnung."""
    _, lesen, _ablehnung, vorlagen = next(e for e in LESER if e[0] == name)
    lesen(vorlagen[0])


def test_vollstaendige_uebernahme_liest_oder_lehnt_ab(tmp_path):
    """Kopf einer Exportdatei (JSON oder ZIP) für die Vollübernahme."""
    from django.core.files.storage import FileSystemStorage

    from datatransfer import dump, load

    kopf = json.dumps(
        {"format": dump.FORMAT, "version": dump.VERSION, "permissions_schema": 2, "unit": {}}
    ).encode()
    vorlagen = [kopf, _zip({dump.JSON_NAME: kopf, "dateien/logo.png": PNG})]
    ablage = FileSystemStorage(location=str(tmp_path))

    class Datei:
        storage = ablage

        def __init__(self, data: bytes):
            self.name = ablage.save("export.bin", io.BytesIO(data))
            self.size = len(data)

        def open(self, mode="rb"):
            return ablage.open(self.name, mode)

    @EINSTELLUNG
    @given(eingaben(vorlagen))
    def lauf(data):
        datei = Datei(data)
        try:
            doc, dateien = load.open_file(datei)
            assert isinstance(doc, dict)
            dateien.has("dateien/logo.png")
            try:
                dateien.read("dateien/logo.png")
            except load.FileProblem:
                pass
        except load.FileProblem:
            pass
        finally:
            ablage.delete(datei.name)

    lauf()
    load.open_file(Datei(vorlagen[0]))
    load.open_file(Datei(vorlagen[1]))


# --- XML wird nur mit dem sicheren Leser gelesen ------------------------------------------

# Stellen, an denen lxml oder xml.etree selbst liest: nur eigene, im Programm erzeugte Daten.
XML_AUSNAHMEN = {
    "billing/hybrid.py": "liest die selbst erzeugte Rechnung (CII) für den PDF-Anhang",
    "music/payouts.py": "liest das mitgelieferte Schema und prüft die selbst erzeugte Meldung",
}
XML_LESEAUFRUF = re.compile(
    r"(?<![\w.])(ET|etree|ElementTree|minidom|pulldom|expat|sax|xml\.sax)\."
    r"(fromstring|parse|parseString|XML|iterparse|ParserCreate|make_parser)\("
)


def test_xml_wird_nur_mit_defusedxml_gelesen():
    """Kein neuer Leser geht an defusedxml vorbei (keine Entitäten, kein Nachladen)."""
    wurzel = Path(__file__).parent.parent
    funde = []
    genutzt = set()
    for datei in sorted(wurzel.rglob("*.py")):
        rel = datei.relative_to(wurzel).as_posix()
        if rel.startswith("tests/") or "/migrations/" in rel:
            continue
        text = datei.read_text(encoding="utf-8")
        sicher = set()
        for zeile in text.splitlines():
            # „from defusedxml import ElementTree“ macht den Namen ElementTree sicher
            if "defusedxml" in zeile and "import" in zeile:
                sicher.update(
                    teil.split(" as ")[-1].strip() for teil in zeile.split("import")[1].split(",")
                )
        for nummer, zeile in enumerate(text.splitlines(), 1):
            treffer = XML_LESEAUFRUF.search(zeile.split("#")[0])
            if not treffer or treffer.group(1) in sicher:
                continue
            if rel in XML_AUSNAHMEN:
                genutzt.add(rel)
            else:
                funde.append(f"{rel}:{nummer}: {zeile.strip()}")
    assert not funde, (
        "XML aus fremder Hand nur mit defusedxml lesen (oder die Stelle mit Begründung in "
        "XML_AUSNAHMEN eintragen):\n" + "\n".join(funde)
    )
    assert genutzt == set(XML_AUSNAHMEN), "XML_AUSNAHMEN: Eintrag ohne Wirkung, bitte entfernen"
