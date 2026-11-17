"""Automatische Vorprüfung eines Nachweises, nur auf dem eigenen Server (kein Fremddienst).

Aus digitalen PDFs (die meisten Hochschulen liefern Bescheinigungen mit Textebene) wird der
Text gelesen und gegen das Mitglied geprüft:

- Name (Vor- und Nachname, Umlaute auch als ae/oe/ue/ss) und, wenn bekannt, Geburtsdatum
- Schlüsselwörter einer Studien- oder Promotionsbescheinigung
- Semester bzw. „gültig bis“ → Vorschlag für „gültig bis“ (Wintersemester bis 31.03.,
  Sommersemester bis 30.09.)
- digitale Signatur: Ist das Dokument seit dem Signieren unverändert, und wer hat signiert?
  Das ist ein Hinweis, keine Vertrauensprüfung der Hochschule.

Ergebnis ist eine Ampel mit Gründen: grün (alles passt), gelb (bitte ansehen), rot (kein
Text lesbar oder Name fehlt). Gespeichert wird nur dieses Ergebnis, nie der gelesene Text.
Fotos werden nicht gelesen (keine Texterkennung); sie sind immer gelb.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import unicodedata

GREEN, YELLOW, RED = "green", "yellow", "red"
MAX_PAGES = 5

KEYWORDS = (
    "immatrikulationsbescheinigung",
    "studienbescheinigung",
    "immatrikuliert",
    "eingeschrieben",
    "studierende",
    "student",
    "enrolment",
    "enrollment",
    "promotion",
    "doktorand",
    "promovierend",
    "doctoral",
)

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _fold(text: str) -> str:
    """Kleinbuchstaben, Umlaute als ae/oe/ue/ss, übrige Akzente weg, Leerraum vereinheitlicht."""
    text = text.lower().translate(_UMLAUTS)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text)


def pdf_text(data: bytes) -> str:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001 - kaputtes oder verschlüsseltes PDF: kein Text
        return ""
    try:
        parts = []
        for i in range(min(len(doc), MAX_PAGES)):
            page = doc[i]
            textpage = page.get_textpage()
            parts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return "\n".join(parts)
    finally:
        doc.close()


_SEMESTER_WINTER = re.compile(
    r"(?:wintersemester|winter semester|wise|ws)\s*(20\d\d)\s*/\s*(\d{2}|20\d\d)"
)
_SEMESTER_SUMMER = re.compile(r"(?:sommersemester|summer semester|sose|ss)\s*(20\d\d)\b")
_UNTIL = re.compile(
    r"(?:gueltig bis|gultig bis|bis zum|bis einschliesslich|valid until|valid through)"
    r"\s*:?\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d\d)"
)


def _date(y: int, m: int, d: int) -> datetime.date | None:
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def suggested_until(folded: str) -> datetime.date | None:
    """Spätestes erkanntes Ende (Semester oder ausdrückliches „gültig bis“)."""
    found: list[datetime.date] = []
    for m in _SEMESTER_WINTER.finditer(folded):
        end_year = int(m.group(2))
        end_year = end_year if end_year > 99 else 2000 + end_year
        if end_year == int(m.group(1)) + 1:
            found.append(datetime.date(end_year, 3, 31))
    for m in _SEMESTER_SUMMER.finditer(folded):
        found.append(datetime.date(int(m.group(1)), 9, 30))
    for m in _UNTIL.finditer(folded):
        day = _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if day:
            found.append(day)
    return max(found) if found else None


def _birth_variants(birth: datetime.date) -> list[str]:
    return [
        f"{birth.day:02d}.{birth.month:02d}.{birth.year}",
        f"{birth.day}.{birth.month}.{birth.year}",
        birth.isoformat(),
        f"{birth.day:02d}/{birth.month:02d}/{birth.year}",
    ]


# --- Signatur ---

_MESSAGE_DIGEST = bytes.fromhex("06092a864886f70d010904")
_BYTE_RANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")


def _der_length(data: bytes, pos: int) -> tuple[int, int]:
    first = data[pos]
    if first < 0x80:
        return first, pos + 1
    count = first & 0x7F
    return int.from_bytes(data[pos + 1 : pos + 1 + count], "big"), pos + 1 + count


def signature_info(data: bytes) -> dict | None:
    """Erste Signatur: unverändert seit dem Signieren? Wer hat signiert? None ohne Signatur."""
    match = _BYTE_RANGE.search(data)
    if match is None:
        return None
    a, b, c, d = (int(x) for x in match.groups())
    if a != 0 or b <= 0 or c <= b or c + d > len(data):
        return {"intact": False, "signer": ""}
    signed = data[a : a + b] + data[c : c + d]
    hex_part = data[a + b : c].strip(b"<> \r\n\t")
    try:
        cms = bytes.fromhex(hex_part.decode("ascii"))
    except ValueError:
        return {"intact": False, "signer": ""}
    intact = False
    at = cms.find(_MESSAGE_DIGEST)
    if at >= 0:
        try:
            pos = at + len(_MESSAGE_DIGEST)
            if cms[pos] == 0x31:  # SET
                _, pos = _der_length(cms, pos + 1)
                if cms[pos] == 0x04:  # OCTET STRING
                    size, pos = _der_length(cms, pos + 1)
                    digest = cms[pos : pos + size]
                    for algo in ("sha256", "sha512", "sha384", "sha1"):
                        if hashlib.new(algo, signed).digest() == digest:
                            intact = True
                            break
        except IndexError:
            intact = False
    signer = ""
    try:
        from cryptography.hazmat.primitives.serialization import pkcs7
        from cryptography.x509.oid import NameOID

        certs = pkcs7.load_der_pkcs7_certificates(cms.rstrip(b"\x00"))
        for cert in certs:
            subject = cert.subject
            names = subject.get_attributes_for_oid(
                NameOID.ORGANIZATION_NAME
            ) or subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if names and cert.extensions:
                basic = [e for e in cert.extensions if e.oid.dotted_string == "2.5.29.19"]
                if basic and getattr(basic[0].value, "ca", False):
                    continue  # Zertifizierungsstelle, nicht der Signierende
            if names:
                signer = str(names[0].value)[:200]
                break
    except Exception:  # noqa: BLE001 - unbekanntes Format: ohne Namen
        signer = ""
    return {"intact": intact, "signer": signer}


# --- Prüfung ---


def check(
    data: bytes,
    content_type: str,
    *,
    first_name: str,
    last_name: str,
    birth_date: datetime.date | None,
    needed_until: datetime.date,
) -> dict:
    """Ampel mit Gründen und Vorschlägen; ``needed_until``: so lange muss er mindestens gelten."""
    reasons: list[str] = []
    result: dict = {"level": YELLOW, "reasons": reasons}
    if content_type != "application/pdf":
        reasons.append("photo")
        return result
    sig = signature_info(data)
    if sig is not None:
        result["signature"] = sig
    text = _fold(pdf_text(data))
    if len(text.strip()) < 20:
        result["level"] = RED
        reasons.append("no_text")
        return result
    name_ok = _fold(last_name) in text and all(
        part in text for part in _fold(first_name).split()[:1]
    )
    if not name_ok:
        reasons.append("name_missing")
    else:
        reasons.append("name_ok")
    if birth_date is not None:
        found_birth = any(v in text for v in _birth_variants(birth_date))
        reasons.append("birth_ok" if found_birth else "birth_missing")
    keyword = next((k for k in KEYWORDS if k in text), "")
    reasons.append("keyword_ok" if keyword else "keyword_missing")
    if "doktorand" in text or "promotion" in text or "promovierend" in text or "doctoral" in text:
        result["kind_hint"] = "doctoral"
    elif keyword:
        result["kind_hint"] = "study"
    until = suggested_until(text)
    if until is not None:
        result["valid_until"] = until.isoformat()
        if until < needed_until:
            reasons.append("expired")
        else:
            reasons.append("valid_ok")
    else:
        reasons.append("valid_missing")
    if not name_ok:
        result["level"] = RED
    elif keyword and until is not None and until >= needed_until:
        result["level"] = GREEN
    return result
