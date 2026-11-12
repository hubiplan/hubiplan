"""Gesamtaudit 11.11.2026, Fachfrage 5: Abschluss aufheben zu zweit (Option je Verein);
Buchungstext und Partner festgeschriebener Buchungen schützt die Anwendung."""

import pytest

from finance.models import ReopenedClosing, YearClosing

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "billing"]
    club.save()
    return club


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


@pytest.fixture
def vorstand(api, board_a):
    return api(board_a)


@pytest.fixture
def kasse(api, club):
    user = make_user("kasse@example.org")
    give_role(user, club, ["finance.view", "finance.edit"], name="Kassierer")
    return api(user)


@pytest.fixture
def setup(vorstand, fin):
    bank = vorstand.post(
        f"{fin}/accounts/", {"name": "Girokonto", "opening_date": "2024-01-01"}, content_type=JSON
    ).json()["id"]
    cat = vorstand.post(
        f"{fin}/categories/", {"name": "Spenden", "kind": "income"}, content_type=JSON
    ).json()["id"]
    booking = vorstand.post(
        f"{fin}/bookings/",
        {
            "date": "2024-06-01",
            "kind": "income",
            "amount": "20",
            "account": bank,
            "category": cat,
            "text": "Spende Sommerfest",
        },
        content_type=JSON,
    )
    assert booking.status_code == 201, booking.content
    return {"bank": bank, "cat": cat, "booking": booking.json()["id"]}


def _close(client, fin):
    resp = client.post(f"{fin}/closings/", {"year": 2024}, content_type=JSON)
    assert resp.status_code == 201, resp.content


def _year(data):
    return {y["year"]: y for y in data["years"]}[2024]


def test_ohne_option_wie_bisher(vorstand, kasse, fin, setup):
    _close(vorstand, fin)
    assert vorstand.get(f"{fin}/closings/").json()["reopen_four_eyes"] is False
    # Kasse allein darf nicht, Vorstand mit Rollenverwaltung schon
    assert (
        kasse.delete(f"{fin}/closings/?jahr=2024", {"reason": "Beleg fehlt"}, JSON).status_code
        == 403
    )
    resp = vorstand.delete(f"{fin}/closings/?jahr=2024", {"reason": "Beleg fehlt"}, JSON)
    assert resp.status_code == 200, resp.content
    assert not YearClosing.objects.exists()


def test_vier_augen_kasse_beantragt_vorstand_bestaetigt(vorstand, kasse, fin, setup, club):
    _close(vorstand, fin)
    # nur Vorstand mit Rollenverwaltung schaltet um
    assert kasse.patch(f"{fin}/settings/", {"reopen_four_eyes": True}, JSON).status_code == 403
    resp = vorstand.patch(f"{fin}/settings/", {"reopen_four_eyes": True}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["reopen_four_eyes"] is True

    url = f"{fin}/closings/?jahr=2024"
    assert kasse.delete(url, {"reason": ""}, JSON).status_code == 400
    resp = kasse.delete(url, {"reason": "Beleg nachgereicht"}, JSON)
    assert resp.status_code == 200, resp.content
    request = _year(resp.json())["reopen_request"]
    assert request["reason"] == "Beleg nachgereicht" and request["mine"] is True
    assert YearClosing.objects.filter(year=2024).exists()

    # die Kasse kann nicht selbst bestätigen
    assert kasse.delete(url, {"confirm": True}, JSON).status_code == 403
    # ein zweiter Antrag geht nicht, ohne Bestätigung passiert nichts
    assert vorstand.delete(url, {"reason": "noch einmal"}, JSON).status_code == 400
    assert _year(vorstand.get(f"{fin}/closings/").json())["reopen_request"]["mine"] is False

    resp = vorstand.delete(url, {"confirm": True}, JSON)
    assert resp.status_code == 200, resp.content
    assert not YearClosing.objects.filter(year=2024).exists()
    archived = ReopenedClosing.objects.get()
    assert "Beleg nachgereicht" in archived.reason
    assert "bestätigt" in archived.reason


def test_vorstand_mit_kasse_braucht_zweite_person(vorstand, kasse, fin, setup, club):
    _close(vorstand, fin)
    vorstand.patch(f"{fin}/settings/", {"reopen_four_eyes": True}, JSON)
    url = f"{fin}/closings/?jahr=2024"
    assert vorstand.delete(url, {"reason": "Tippfehler"}, JSON).status_code == 200
    # auch mit allen Rechten nicht allein
    assert vorstand.delete(url, {"confirm": True}, JSON).status_code == 403
    # die Kasse ohne Rollenverwaltung bestätigt nicht
    assert kasse.delete(url, {"confirm": True}, JSON).status_code == 403
    # zurückziehen: wer beantragt hat
    resp = vorstand.delete(url, {"withdraw": True}, JSON)
    assert resp.status_code == 200
    assert _year(resp.json())["reopen_request"] is None
    assert YearClosing.objects.filter(year=2024).exists()


def test_text_und_partner_festgeschriebener_buchungen(vorstand, fin, setup, club):
    from billing.models import BusinessPartner
    from core.tenancy import tenant_context

    with tenant_context(club.pk):
        partner = BusinessPartner.objects.create(
            organization=club,
            name="Getränke Beispiel GmbH",
            roles=["supplier"],
            bank={},
            details={"name": "Getränke Beispiel GmbH"},
        )
    resp = vorstand.patch(f"{fin}/settings/", {"locked_until": "2024-12-31"}, JSON)
    assert resp.status_code == 200, resp.content
    booking = f"{fin}/bookings/{setup['booking']}/"
    for change in ({"text": "geändert"}, {"partner": partner.pk}):
        resp = vorstand.patch(booking, change, JSON)
        assert resp.status_code == 400, (change, resp.content)
        assert "festgeschrieben" in str(resp.json())
