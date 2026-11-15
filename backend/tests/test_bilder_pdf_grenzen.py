"""Hochgeladene Bilder nie als EPS, PDF-Anhänge mit Grenzen (Gesamtaudit 15.11., PUB-01/PUB-02)."""

from __future__ import annotations

import io
import zlib

import pytest
from PIL import Image, UnidentifiedImageError

pytestmark = pytest.mark.django_db

EPS = b"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 20 20
%%EndComments
newpath 0 0 moveto 20 20 lineto 0 20 lineto closepath fill
showpage
%%EOF
"""


def test_eps_wird_nicht_geoeffnet():
    with pytest.raises(UnidentifiedImageError):
        Image.open(io.BytesIO(EPS))


def test_unterschrift_als_eps_abgelehnt():
    from letterhead import docx

    assert docx.load_picture(EPS, "unterschrift") is None


def test_unterschrift_als_png_geht():
    from letterhead import docx

    out = io.BytesIO()
    Image.new("RGB", (20, 10), "black").save(out, "PNG")
    picture = docx.load_picture(out.getvalue(), "unterschrift")
    assert picture is not None and picture.data.startswith(b"\x89PNG")


def _mpo() -> bytes:
    """iPhone-Foto: JPEG mit Zusatzbild (MPO), wie in tests/test_photos.py."""
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(
        buf, "MPO", save_all=True, append_images=[Image.new("RGB", (6, 4))]
    )
    return buf.getvalue()


def test_unterschrift_als_iphone_foto_mpo_geht():
    from letterhead import docx

    data = _mpo()
    with Image.open(io.BytesIO(data)) as probe:
        assert probe.format == "MPO"
    picture = docx.load_picture(data, "unterschrift")
    assert picture is not None and picture.data[1:4] == b"PNG"


def test_verbund_logo_als_mpo_und_eps(monkeypatch):
    """Logo einer Partnerinstanz: MPO wird übernommen, EPS nicht."""
    import base64

    from peering import packet_unit

    class Logo:
        def __init__(self):
            self.name = ""

        def save(self, name, content, save=True):
            self.name = name

        def __bool__(self):
            return bool(self.name)

    class Org:
        uuid = "0000"

        def __init__(self):
            self.logo = Logo()

    monkeypatch.setattr(packet_unit, "delete_on_commit", lambda *a, **k: None)
    for data, erwartet in ((_mpo(), True), (EPS, False)):
        org = Org()
        packet_unit._logo(org, base64.b64encode(data).decode())
        assert bool(org.logo) == erwartet, erwartet


def _pdf_mit_anhang(inhalt_komprimiert: bytes, name: bytes = b"factur-x.xml") -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [("
        + name
        + b") 4 0 R] >> >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
        b"<< /Type /Filespec /F (" + name + b") /UF (" + name + b") /EF << /F 5 0 R >> >>",
        b"<< /Type /EmbeddedFile /Filter /FlateDecode /Length "
        + str(len(inhalt_komprimiert)).encode()
        + b" >>\nstream\n"
        + inhalt_komprimiert
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_bombe_liefert_kein_xml():
    from finance.einvoice import xml_from_pdf

    pdf = _pdf_mit_anhang(zlib.compress(b" " * (64 * 1024 * 1024), 9))
    assert len(pdf) < 200 * 1024
    assert xml_from_pdf(pdf) is None


def test_pdf_mit_kleinem_xml_geht():
    from finance.einvoice import xml_from_pdf

    xml = b"<?xml version='1.0'?><rsm:CrossIndustryInvoice/>"
    assert xml_from_pdf(_pdf_mit_anhang(zlib.compress(xml))) == xml
