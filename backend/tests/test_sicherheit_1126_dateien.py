"""Sicherheitsprüfung 26.11.2026, Paket 4: Dateien, Virenprüfung, Mail-Eingang (erfunden)."""

from __future__ import annotations

import datetime
import io
import zipfile
from email.message import EmailMessage

import pytest
from django.core.exceptions import ValidationError
from django.http import HttpResponse

from circulars import inbound
from core import filecheck, virenscan
from documents import notation
from feeproofs import precheck

from .test_beitragsnachweise import bescheinigung, pdf

NEEDED = datetime.date(2026, 3, 31)
BIRTH = datetime.date(1980, 5, 17)


# --- B-H07: Vorprüfung der Nachweise ---


def _check(data: bytes, birth=BIRTH) -> dict:
    return precheck.check(
        data,
        "application/pdf",
        first_name="Anna",
        last_name="Muster",
        birth_date=birth,
        needed_until=NEEDED,
    )


def test_vorpruefung_liest_pdf_im_eigenen_prozess():
    assert "immatrikulationsbescheinigung" in precheck.pdf_text(bescheinigung()).lower()
    assert _check(bescheinigung())["level"] == "green"


def test_kaputte_datei_beendet_nur_die_vorpruefung():
    assert precheck.pdf_text(b"kein PDF") == ""
    assert precheck.pdf_text(b"%PDF-1.7\n" + b"\x00\xff" * 5000) == ""
    assert _check(b"%PDF-1.7\n" + b"\x00\xff" * 5000)["level"] == "red"


def test_kindprozess_mit_zeitgrenze(monkeypatch):
    import subprocess

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    assert precheck.pdf_text(bescheinigung()) == ""


def test_ohne_geburtsdatum_im_nachweis_kein_gruen():
    res = _check(bescheinigung(birth="01.01.1999"))
    assert "birth_missing" in res["reasons"] and res["level"] == "yellow"


def test_signatur_mit_angehaengten_daten_ist_nicht_intakt():
    body = pdf("Immatrikulationsbescheinigung")
    signed = body + b"\n/ByteRange [0 10 20 5]\n" + b"x" * 400
    info = precheck.signature_info(signed)
    assert info == {"intact": False, "verified": False, "signer": ""}


def test_signatur_wird_nie_als_geprueft_ausgewiesen(monkeypatch):
    monkeypatch.setattr(
        precheck, "signature_info", lambda data: {"intact": False, "verified": False, "signer": ""}
    )
    # Eine Signatur, die nicht zum Inhalt passt, verhindert Grün
    assert _check(bescheinigung())["level"] == "yellow"


# --- C-M02: Virenprüfung ---


class _ZuGross:
    too_big = True

    def feed(self, data):
        pass

    def result(self):
        return None


def test_eingang_zu_gross_fuer_die_pruefung_wird_nicht_uebernommen(monkeypatch, settings):
    monkeypatch.setattr(virenscan, "enabled", lambda: True)
    monkeypatch.setattr(virenscan, "Stream", _ZuGross)
    settings.VIRUS_SCAN_REQUIRED = True
    assert virenscan.inbound_ok(b"x" * 10, "gross.pdf", "Test") is False
    # Uploads angemeldeter Personen und die Datenübernahme bleiben wie bisher
    virenscan.scan_bytes(b"x" * 10, "gross.pdf")
    settings.VIRUS_SCAN_REQUIRED = False
    assert virenscan.inbound_ok(b"x" * 10, "gross.pdf", "Test") is True


def test_notenarchiv_mit_falscher_groessenangabe():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "noten.musicxml", b"<score-partwise/>" + b" " * (notation.MAX_UNZIPPED + 10)
        )
    with pytest.raises(ValidationError):
        notation._unzip_mxl(buf.getvalue())


# --- C-L01: erzeugte Dateien und Fotos ---


def _through_middleware(response):
    return filecheck.SafeFileMiddleware(lambda request: response)(None)


def test_erzeugtes_svg_laeuft_nie_als_seite():
    response = _through_middleware(HttpResponse("<svg/>", content_type="image/svg+xml"))
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_gewoehnliche_antworten_bleiben_ohne_sandbox():
    for ctype in ("application/json", "text/html"):
        assert "Content-Security-Policy" not in _through_middleware(
            HttpResponse("{}", content_type=ctype)
        )
    pdf_response = HttpResponse(b"%PDF", content_type="application/pdf")
    pdf_response["Content-Disposition"] = 'inline; filename="a.pdf"'
    assert "Content-Security-Policy" not in _through_middleware(pdf_response)


def test_foto_am_inhalt_erkannt():
    assert filecheck.is_image(b"\xff\xd8\xff\xe0" + b"\x00" * 28)
    assert filecheck.is_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)
    assert filecheck.is_image(b"\x00\x00\x00\x18ftypavif" + b"\x00" * 20)
    assert not filecheck.is_image(b"<html><script>alert(1)</script>")
    assert not filecheck.is_image(b"%PDF-1.7")


# --- C-M01: Absender im Mail-Eingang ---


def _mail(*froms: str, results: str = "") -> EmailMessage:
    msg = EmailMessage()
    for value in froms:
        msg["From"] = value
    if results:
        msg["Authentication-Results"] = results
    return msg


def test_absender_nur_wenn_eindeutig():
    assert inbound.from_address(_mail("Anna <anna@example.org>")) == "anna@example.org"
    assert inbound.from_address(_mail("anna@example.org, boese@example.net")) == ""
    assert inbound.from_address(_mail()) == ""


def test_dmarc_ergebnis_muss_zur_absenderdomain_gehoeren(settings):
    settings.MAIL_AUTHSERV_ID = "mx.example.org"
    ok = "mx.example.org; dmarc=pass header.from=example.org"
    assert inbound.dmarc_passed(_mail("anna@example.org", results=ok))
    assert inbound.dmarc_passed(_mail("anna@example.org", results="mx.example.org; dmarc=pass"))
    other = "mx.example.org; dmarc=pass header.from=example.net"
    assert not inbound.dmarc_passed(_mail("anna@example.org", results=other))
    assert not inbound.dmarc_passed(_mail("a@example.org, b@example.net", results=ok))
