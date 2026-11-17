"""Excel-Import der Geschäftspartner mit Entpackgrenze (Gesamtaudit 15.11., PUB-09).

openpyxl lädt die gemeinsamen Texte einer Excel-Datei vollständig. Eine kleine, stark
gepackte Datei konnte so den Speicher füllen. Jetzt gilt dieselbe Grenze wie beim
Mitgliederimport. Erfundene Daten.
"""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

pytestmark = pytest.mark.django_db


@pytest.fixture
def base(orgs):
    return f"/api/orgs/{orgs['a'].pk}/billing/"


def _bombe() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/sharedStrings.xml", "a" * (8 * 1024 * 1024))
    return out.getvalue()


def test_stark_gepackte_datei_wird_abgewiesen(api, board_a, base):
    content = _bombe()
    assert len(content) < 100 * 1024
    resp = api(board_a).post(
        f"{base}partners/import/", {"file": SimpleUploadedFile("p.xlsx", content)}
    )
    assert resp.status_code == 400
    assert "entpackt zu groß" in str(resp.json())


def test_normale_datei_geht_weiter(api, board_a, base):
    book = Workbook()
    sheet = book.active
    sheet.append(["Nummer", "Name"])
    sheet.append(["", "Getränke Beispiel GmbH"])
    out = io.BytesIO()
    book.save(out)
    resp = api(board_a).post(
        f"{base}partners/import/", {"file": SimpleUploadedFile("p.xlsx", out.getvalue())}
    )
    assert resp.status_code in (200, 201), resp.content
    assert "entpackt" not in str(resp.content)
