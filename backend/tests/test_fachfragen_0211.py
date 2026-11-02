"""Fachfragen aus dem Gesamtaudit 02.11. (erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import io
import json
import zipfile

import pytest

from finance.models import Booking

from .test_aufbewahrungsende import _private, fin, heute, jahr2025, retention_of  # noqa: F401
from .test_m9_billing import JSON, base, c, club, members, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db


# --- FQ10: Löschsperre je Geschäftsjahr ---


class TestLoeschsperre:
    def url(self, fin):
        return f"{fin}/closings/aufbewahrung/"

    def test_sperre_verhindert_bereinigung(self, c, fin, club, jahr2025, monkeypatch):
        resp = c.post(
            self.url(fin), {"year": 2025, "hold": "Betriebsprüfung 2036"}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
        info = retention_of(c, fin)
        assert info["hold"] == "Betriebsprüfung 2036"
        assert info["hold_by"] and info["hold_at"]

        heute(monkeypatch, datetime.date(2036, 1, 1))
        resp = c.post(self.url(fin), {"year": 2025}, content_type=JSON)
        assert resp.status_code == 400
        assert "Löschsperre" in str(resp.json())
        assert Booking.objects.get(pk=jahr2025).counterparty == "Erika Musterfrau"

        # Aufheben, danach geht es wieder
        resp = c.post(self.url(fin), {"year": 2025, "hold": ""}, content_type=JSON)
        assert resp.status_code == 200
        assert retention_of(c, fin)["hold"] == ""
        resp = c.post(self.url(fin), {"year": 2025}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert Booking.objects.get(pk=jahr2025).counterparty == ""

    def test_sperre_wird_protokolliert(self, c, fin, club, jahr2025):
        from audit.models import AuditEntry
        from core.tenancy import rls_bypass

        c.post(self.url(fin), {"year": 2025, "hold": "Rechtsstreit"}, content_type=JSON)
        with rls_bypass():
            entry = AuditEntry.objects.filter(organization=club)
            assert any("Löschsperre" in e.changes for e in entry)

    def test_nur_abgeschlossene_jahre(self, c, fin, setup):
        resp = c.post(self.url(fin), {"year": 2025, "hold": "Prüfung"}, content_type=JSON)
        assert resp.status_code == 400

    def test_grund_muss_text_sein(self, c, fin, jahr2025):
        resp = c.post(self.url(fin), {"year": 2025, "hold": 5}, content_type=JSON)
        assert resp.status_code == 400


# --- FQ13: Auskunft bei Sammelrechnung ---


def test_auskunft_aus_sammelrechnung_nur_eigene_posten(c, base, club, members):
    run = start_run(c, base).json()
    c.post(f"{base}/runs/{run['id']}/finalize/")
    resp = c.get(f"/api/orgs/{club.pk}/members/{members['z1'].pk}/auskunft/")
    assert resp.status_code == 200, resp.content[:300]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    rows = json.loads(zf.read("rechnungen.json"))
    assert len(rows) == 1
    row = rows[0]
    assert row["sammelrechnung"] is True and row["number"]
    assert row["positionen"] and all(
        p["membership_id"] == members["z1"].pk for p in row["positionen"]
    )
    # Nichts von Zita, keine Anschrift, keine Zahlungen, kein PDF mit allen Posten
    assert "Zita" not in zf.read("rechnungen.json").decode()
    assert "recipient_address" not in row and "zahlungen" not in row and "total" not in row
    assert "rechnungen.pdf" not in zf.namelist()
