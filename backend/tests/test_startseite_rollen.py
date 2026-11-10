"""Startseite je Rolle (S-04) und Einrichtung bündeln (S-02): Stand der Einrichtung und neue
Quellen für „Zu erledigen“, jeweils nur mit passendem Recht."""

import datetime
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.tenancy import tenant_context
from finance.models import Account, BankStatement, Booking
from members.models import MemberType

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _ohne_zwischenspeicher():
    cache.clear()
    yield
    cache.clear()


def status(client, org):
    resp = client.get(f"/api/orgs/{org.pk}/setup-status/")
    assert resp.status_code == 200, resp.content
    return resp.json()["items"]


def tasks(client, org, kind=None):
    rows = client.get(f"/api/orgs/{org.pk}/open-tasks/").json()["items"]
    return [r for r in rows if kind is None or r["kind"] == kind]


def _kasse(org):
    """Bank- und Barkonto mit einer Buchung ohne Beleg und einem Auszug von vor zwei Monaten."""
    today = timezone.localdate()
    with tenant_context(org.pk):
        bank = Account.objects.create(
            organization=org, name="Girokonto", kind="bank", opening_date=datetime.date(2020, 1, 1)
        )
        cash = Account.objects.create(
            organization=org,
            name="Barkasse",
            kind="cash",
            opening_date=datetime.date(2020, 1, 1),
            opening_balance=Decimal("100.00"),
        )
        Booking.objects.create(
            organization=org,
            account=cash,
            year=org.fiscal_year_of(today),
            number=1,
            date=today,
            kind="income",
            amount=Decimal("12.30"),
            text="Getränke",
        )
        old_end = today.replace(day=1) - datetime.timedelta(days=40)
        BankStatement.objects.create(
            organization=org,
            account=bank,
            file_name="auszug.xml",
            date_from=old_end - datetime.timedelta(days=27),
            date_to=old_end,
            closing_balance=Decimal("8904.17"),
        )
    return bank, cash


def test_stand_der_einrichtung(api, orgs, board_a):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "finance", "billing"})
    org.street, org.postal_code, org.city = "", "", ""
    org.save()
    c = api(board_a)
    items = status(c, org)
    assert items["/einstellungen/organisation"]["done"] is False
    assert items["/mitglieder/einrichtung/mitgliedsarten"] == {
        "required": True,
        "done": False,
        "count": 0,
    }
    assert items["/finanzen/einrichtung/mahnstufen"]["required"] is True
    assert items["/mitglieder/einrichtung/zusatzfelder"]["required"] is False

    MemberType.objects.create(organization=org, name="aktiv", active=True)
    org.street, org.postal_code, org.city = "Musterweg 1", "12345", "Musterstadt"
    org.save()
    items = status(c, org)
    assert items["/mitglieder/einrichtung/mitgliedsarten"]["count"] == 1
    assert items["/mitglieder/einrichtung/mitgliedsarten"]["done"] is True
    assert items["/einstellungen/organisation"]["done"] is True


def test_stand_nur_mit_leserecht(api, orgs):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "finance"})
    org.save()
    kasse = make_user("kasse@example.org")
    give_role(kasse, org, permissions=["finance.view"], name="Kasse")
    items = status(api(kasse), org)
    assert set(items) == {"/finanzen/einrichtung/konten", "/finanzen/einrichtung/kategorien"}
    # Ohne Pflichtpunkt mit Recht auch kein Eintrag unter „Zu erledigen“ für andere Bereiche
    assert all(set(t["paths"]) <= set(items) for t in tasks(api(kasse), org, "setup_incomplete"))


def test_fehlende_einrichtung_unter_zu_erledigen(api, orgs, board_a):
    org = orgs["a"]
    org.street, org.postal_code, org.city = "", "", ""
    org.save()
    rows = tasks(api(board_a), org, "setup_incomplete")
    assert len(rows) == 1
    assert rows[0]["link"] == "/einstellungen/einrichtung"
    assert "/einstellungen/organisation" in rows[0]["paths"]
    # Das Impressum steht auf der Startseite unter „Hinweise“, nicht doppelt
    assert "/einstellungen/impressum" not in rows[0]["paths"]

    leser = make_user("lesen@example.org")
    give_role(leser, org, permissions=["members.view"], name="Lesen")
    paths = [p for r in tasks(api(leser), org, "setup_incomplete") for p in r["paths"]]
    assert "/einstellungen/organisation" not in paths


def test_kasse_buchungen_ohne_beleg_und_fehlender_auszug(api, orgs, board_a):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "finance"})
    org.save()
    bank, _ = _kasse(org)
    c = api(board_a)
    rows = tasks(c, org, "bookings_without_receipt")
    assert [r["title"] for r in rows] == ["1 Buchung ohne Beleg"]
    assert rows[0]["link"] == "/finanzen/kassenbuch?ohne_beleg=1"
    assert rows[0]["area"] == "finance"
    missing = tasks(c, org, "statement_missing")
    if timezone.localdate().day >= 5:
        assert [r["ref"] for r in missing] == [bank.pk]
        assert missing[0]["link"] == "/finanzen/kontoauszuege"
    else:
        assert missing == []

    pruefer = make_user("pruefer@example.org")
    give_role(pruefer, org, permissions=["finance.view"], name="Kassenprüfer")
    assert tasks(api(pruefer), org, "bookings_without_receipt") == []
    assert tasks(api(pruefer), org, "statement_missing") == []


def test_schwerpunkt_aus_den_rollen(api, orgs, board_a):
    """Kassenrechte allein machen niemanden zur Kasse: Vollrechte (Rollen vergeben) zählen nicht."""
    org = orgs["a"]

    def focus(user):
        rows = api(user).get("/api/me/organizations/").json()
        return next(o for o in rows if o["id"] == org.pk)["home_focus"]

    assert focus(board_a) == []
    kasse = make_user("kassierer@example.org")
    give_role(kasse, org, permissions=["finance.view", "finance.edit"], name="Kassierer")
    assert focus(kasse) == ["finance"]
    # Vorsitz und Kasse zugleich: die Kassenrolle zählt
    give_role(board_a, org, permissions=["finance.edit", "billing.edit"], name="Kassierer")
    assert focus(board_a) == ["finance"]


def test_schnellaktionen_ausblenden(api, board_a):
    c = api(board_a)
    assert c.get("/api/me/home-actions/").json() == {"hidden": [], "chosen": {}}
    resp = c.put(
        "/api/me/home-actions/",
        {"hidden": ["termin", "termin", "*"]},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json() == {"hidden": ["*", "termin"], "chosen": {}}
    board_a.refresh_from_db()
    assert board_a.home_actions_hidden == ["*", "termin"]
    assert (
        c.put(
            "/api/me/home-actions/", {"hidden": ["<b>"]}, content_type="application/json"
        ).status_code
        == 400
    )
    assert c.put(
        "/api/me/home-actions/", {"hidden": []}, content_type="application/json"
    ).json() == {"hidden": [], "chosen": {}}
    board_a.refresh_from_db()
    assert board_a.home_actions_hidden is None


def test_schnellaktionen_waehlen(api, board_a):
    c = api(board_a)

    def put(body):
        return c.put("/api/me/home-actions/", body, content_type="application/json")

    resp = put({"chosen": {"o12": ["aufgabe", "termin", "aufgabe"], "d3": ["einheit-brief"]}})
    assert resp.status_code == 200, resp.content
    # Reihenfolge bleibt, doppelte fallen weg; „hidden“ bleibt unberührt
    assert resp.json() == {
        "hidden": [],
        "chosen": {"d3": ["einheit-brief"], "o12": ["aufgabe", "termin"]},
    }
    # Nur genannte Bereiche ändern sich, null stellt den Vorschlag wieder her
    assert put({"chosen": {"d3": None, "o12": []}}).json()["chosen"] == {"o12": []}
    assert put({"hidden": ["*"]}).json() == {"hidden": ["*"], "chosen": {"o12": []}}
    board_a.refresh_from_db()
    assert board_a.home_actions == {"o12": []}
    assert put({"chosen": {"x1": ["termin"]}}).status_code == 400
    assert put({"chosen": {"o1": ["<b>"]}}).status_code == 400
    assert put({"chosen": {"o1": ["a"] * 13}}).status_code == 400
    assert put({"chosen": {"o12": None}}).json()["chosen"] == {}
    board_a.refresh_from_db()
    assert board_a.home_actions is None
