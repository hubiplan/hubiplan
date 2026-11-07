"""Kassenprüfung als Ablauf (Konzept vereinskasse-steuern, S6); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import cash_audit
from finance.models import Account, Booking, CashAudit, Category

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members"]
    club.save()
    return club


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


@pytest.fixture
def kasse(api, board_a):
    return api(board_a)


@pytest.fixture
def pruefer(api, club):
    user = make_user("pruefer@example.org", first_name="Erika", last_name="Musterfrau")
    with tenant_context(club.pk):
        give_role(user, club, ["finance.view"], name="Kassenprüfer", valid_until=D(2099, 3, 31))
    return api(user)


@pytest.fixture
def buchungen(club):
    """Zwölf Buchungen im Geschäftsjahr 2025 auf dem Girokonto."""
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2024, 1, 1)
        )
        cat = Category.objects.create(organization=club, name="Vereinsbedarf")
        for n in range(1, 13):
            Booking.objects.create(
                organization=club,
                year=2025,
                number=n,
                date=D(2025, n, 5),
                kind="expense" if n % 2 else "income",
                amount=Decimal(100 * n),
                account=account,
                category=cat,
                text=f"Buchung {n}",
            )
    return account


def anlegen(kasse, fin, **extra):
    resp = kasse.post(
        f"{fin}/audits/",
        {"year": 2025, "auditors": "Erika Musterfrau", "sample_size": 8, **extra},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_auftrag_zieht_stichproben_und_konten(kasse, fin, buchungen):
    data = anlegen(kasse, fin)
    assert data["label"] == "2025"
    assert len(data["samples"]) == 8
    # Die fünf größten Ausgaben sind immer dabei (11, 9, 7, 5, 3 × 100 €)
    numbers = {s["number"] for s in data["samples"]}
    assert {"2025-0011", "2025-0009", "2025-0007", "2025-0005", "2025-0003"} <= numbers
    assert [a["name"] for a in data["accounts"]] == ["Girokonto"]
    # Einnahmen 2+4+…+12 = 4.200 €, Ausgaben 1+3+…+11 = 3.600 € (× 100)
    assert data["accounts"][0]["book_balance"] == "600.00"
    assert data["facts"]["bookings"] == 12
    assert data["facts"]["without_receipt"] == 12
    assert data["can_manage"] is True and data["can_audit"] is False
    assert data["access"] == []
    # Ein Auftrag je Geschäftsjahr
    resp = kasse.post(f"{fin}/audits/", {"year": 2025}, content_type=JSON)
    assert resp.status_code == 400


def test_nur_pruefer_haken_ab(kasse, pruefer, fin, buchungen):
    data = anlegen(kasse, fin)
    sample = data["samples"][0]["id"]
    # Die Kasse prüft sich nicht selbst
    resp = kasse.post(f"{fin}/audits/{data['id']}/check/", {"sample": sample, "result": "ok"}, JSON)
    assert resp.status_code == 403
    # Der Prüfer legt keinen Auftrag an
    assert pruefer.post(f"{fin}/audits/", {"year": 2024}, JSON).status_code == 403
    resp = pruefer.post(
        f"{fin}/audits/{data['id']}/check/", {"sample": sample, "result": "ok"}, JSON
    )
    assert resp.status_code == 200, resp.content
    row = next(s for s in resp.json()["samples"] if s["id"] == sample)
    assert row["result"] == "ok" and row["checked_by"] == "Erika Musterfrau"
    # Rückfrage braucht eine Anmerkung
    resp = pruefer.post(
        f"{fin}/audits/{data['id']}/check/", {"sample": sample, "result": "issue"}, JSON
    )
    assert resp.status_code == 400
    # Kontenabgleich mit Differenz
    account = data["accounts"][0]["id"]
    resp = pruefer.post(
        f"{fin}/audits/{data['id']}/check/",
        {"account": account, "statement_balance": "590,00", "note": "Gebühr fehlt"},
        JSON,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["accounts"][0]["difference"] == "-10.00"
    detail = pruefer.get(f"{fin}/audits/{data['id']}/").json()
    assert detail["can_audit"] is True
    assert detail["access"] == [{"name": "Erika Musterfrau", "until": "2099-03-31"}]


def test_abschluss_und_bericht(kasse, pruefer, fin, buchungen):
    data = anlegen(kasse, fin, sample_size=2)
    url = f"{fin}/audits/{data['id']}"
    for s in data["samples"]:
        resp = pruefer.post(f"{url}/check/", {"sample": s["id"], "result": "ok"}, JSON)
        assert resp.status_code == 200
    pruefer.post(
        f"{url}/check/", {"account": data["accounts"][0]["id"], "statement_balance": "600"}, JSON
    )
    # Ohne Empfehlung und mit offenen Prüfpunkten kein Abschluss
    assert pruefer.post(f"{url}/close/", {}, JSON).status_code == 400
    checks = {key: {"result": "ok", "note": ""} for key, _ in cash_audit.CHECKS}
    checks["reserves"] = {"result": "na", "note": "keine Rücklagen"}
    resp = pruefer.patch(
        f"{url}/",
        {"checks": checks, "findings": "Belege ordentlich.", "recommendation": "discharge"},
        JSON,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["open_points"] == 0
    # Die Kasse darf Feststellungen nicht schreiben
    assert kasse.patch(f"{url}/", {"findings": "x"}, JSON).status_code == 403
    resp = pruefer.post(f"{url}/close/", {}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "done"
    # Abgeschlossen: nichts mehr änderbar
    sample = data["samples"][0]["id"]
    assert pruefer.post(f"{url}/check/", {"sample": sample, "result": ""}, JSON).status_code == 400
    pdf = kasse.get(f"{url}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Wieder öffnen nur mit Grund
    assert kasse.post(f"{url}/reopen/", {}, JSON).status_code == 400
    resp = kasse.post(f"{url}/reopen/", {"reason": "Beleg nachgereicht"}, JSON)
    assert resp.json()["status"] == "open"


def test_weitere_stichproben_und_loeschen(kasse, pruefer, fin, club, buchungen):
    data = anlegen(kasse, fin, sample_size=5)
    url = f"{fin}/audits/{data['id']}"
    resp = pruefer.post(f"{url}/draw/", {"count": 50}, JSON)
    assert resp.status_code == 200
    assert len(resp.json()["samples"]) == 12
    assert pruefer.post(f"{url}/draw/", {"count": 5}, JSON).status_code == 400
    # Löschen nur durch die Kasse und nur, solange nichts geprüft ist
    assert pruefer.delete(f"{url}/").status_code == 403
    sample = data["samples"][0]["id"]
    pruefer.post(f"{url}/check/", {"sample": sample, "result": "ok"}, JSON)
    assert kasse.delete(f"{url}/").status_code == 400
    pruefer.post(f"{url}/check/", {"sample": sample, "result": ""}, JSON)
    assert kasse.delete(f"{url}/").status_code == 204
    with tenant_context(club.pk):
        assert not CashAudit.objects.exists()


def test_ungueltige_eingaben(kasse, pruefer, fin, buchungen):
    data = anlegen(kasse, fin)
    url = f"{fin}/audits/{data['id']}"
    assert kasse.patch(f"{url}/", {"sample_size": 0}, JSON).status_code == 400
    assert kasse.patch(f"{url}/", {"meeting": 999999}, JSON).status_code == 400
    assert pruefer.patch(f"{url}/", {"checks": {"x": {}}}, JSON).status_code == 400
    assert pruefer.patch(f"{url}/", {"recommendation": "x"}, JSON).status_code == 400
    resp = pruefer.post(
        f"{url}/check/", {"account": data["accounts"][0]["id"], "statement_balance": "abc"}, JSON
    )
    assert resp.status_code == 400


def test_ohne_kasse_kein_zugriff(api, board_c, club):
    assert api(board_c).get(f"/api/orgs/{club.pk}/finance/audits/").status_code in (403, 404)
