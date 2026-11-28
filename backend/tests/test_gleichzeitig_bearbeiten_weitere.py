# ruff: noqa: F811  (Fixtures als Parameter)
"""Gleichzeitiges Bearbeiten, weitere Bereiche (core/versioning.py): übrige Teile der
Mitgliedsakte, Haushalte, Rechnungen sowie Geschäftspartner mit Vereinbarungen. Wer mit einer
veralteten Fassung speichert, löscht oder festschreibt, bekommt 409. Erfundene Daten."""

import pytest

from members.models import BillingAddress, ContactPerson

from .factories import make_member
from .test_m9_billing import _private, base, c, club, setup, zug  # noqa: F401
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _stale(resp, wort="Eintrag"):
    assert resp.status_code == 409, resp.content
    detail = resp.json()["detail"]
    assert wort in detail and "inzwischen geändert. Bitte neu laden." in detail


@pytest.fixture
def firma(c, club, setup):
    resp = admit_org(c, club, setup["aktiv"])
    assert resp.status_code == 201, resp.json()
    return resp.json()


# --- Mitgliedsakte ------------------------------------------------------------------------


def test_ansprechpartner_veraltete_fassung(c, club, firma):
    url = f"/api/orgs/{club.pk}/members/{firma['id']}/contacts/"
    made = c.post(url, {"last_name": "Muster", "first_name": "Max"}, content_type=JSON)
    assert made.status_code == 201, made.json()
    contact = made.json()
    one = f"{url}{contact['id']}/"
    alt = contact["version"]

    resp = c.patch(one, {"function": "Vorsitz", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] > alt

    _stale(c.patch(one, {"function": "Kasse", "version": alt}, content_type=JSON))
    assert ContactPerson.objects.get(pk=contact["id"]).function == "Vorsitz"
    _stale(c.delete(one, {"version": alt}, content_type=JSON))
    assert ContactPerson.objects.filter(pk=contact["id"]).exists()

    # Ohne Fassung (ältere App) wie bisher
    assert c.patch(one, {"function": "Schrift"}, content_type=JSON).status_code == 200
    neu = c.get(one).json()["version"]
    assert c.delete(one, {"version": neu}, content_type=JSON).status_code == 204


def test_rechnungsanschrift_veraltete_fassung(c, club, firma):
    url = f"/api/orgs/{club.pk}/members/{firma['id']}/billing-address/"
    angaben = {"name": "Musterbau Buchhaltung", "street": "Postfach 1", "city": "Musterstadt"}
    resp = c.put(url, angaben, content_type=JSON)
    assert resp.status_code == 200, resp.content
    alt = resp.json()["billing_address"]["version"]

    resp = c.put(url, {"attention": "Frau Beispiel", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["billing_address"]["version"] > alt

    _stale(c.put(url, {"attention": "Herr Beispiel", "version": alt}, content_type=JSON))
    _stale(c.delete(url, {"version": alt}, content_type=JSON))
    assert BillingAddress.objects.get(membership_id=firma["id"]).attention == "Frau Beispiel"


def test_zeitraum_berichtigen_veraltete_fassung(c, club, setup):
    m = make_member(club, "Erika", "Muster")
    url = f"/api/orgs/{club.pk}/members/{m.pk}/"
    period = c.get(url).json()["periods"][0]
    daten = {"period": period["id"], "exit_date": None, "exit_reason": ""}

    resp = c.post(
        f"{url}correct-period/",
        {**daten, "entry_date": "2019-05-01", "version": period["version"]},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    _stale(
        c.post(
            f"{url}correct-period/",
            {**daten, "entry_date": "2018-05-01", "version": period["version"]},
            content_type=JSON,
        )
    )
    assert c.get(url).json()["periods"][0]["entry_date"] == "2019-05-01"


def test_haushalt_veraltete_fassung(c, club, setup):
    root = f"/api/orgs/{club.pk}/households/"
    made = c.post(root, {"name": "Familie Muster", "kind": "family"}, content_type=JSON)
    assert made.status_code == 201, made.json()
    hh = made.json()
    one = f"{root}{hh['id']}/"

    resp = c.patch(one, {"name": "Familie Beispiel", "version": hh["version"]}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    _stale(c.patch(one, {"name": "Familie Anders", "version": hh["version"]}, content_type=JSON))
    _stale(c.delete(one, {"version": hh["version"]}, content_type=JSON))
    assert c.get(one).json()["name"] == "Familie Beispiel"


# --- Rechnungen ---------------------------------------------------------------------------


def _entwurf(c, base, membership):
    resp = c.post(
        f"{base}/invoices/",
        {
            "recipient_kind": "member",
            "membership": membership.pk,
            "date": "2025-03-01",
            "subject": "Standgebühr",
            "lines": [{"text": "Standgebühr", "amount": "40.00"}],
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def test_rechnungsentwurf_veraltete_fassung(c, club, base, setup):
    m = make_member(club, "Erika", "Muster")
    inv = _entwurf(c, base, m)
    one = f"{base}/invoices/{inv['id']}/"
    alt = inv["version"]

    resp = c.patch(one, {"subject": "Standgebühr 2025", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > alt

    _stale(c.patch(one, {"subject": "Anders", "version": alt}, content_type=JSON), "Rechnung")
    # Festschreiben und Löschen nur in der Fassung, die die Person gesehen hat
    _stale(c.post(f"{one}finalize/", {"version": alt}, content_type=JSON), "Rechnung")
    _stale(c.delete(one, {"version": alt}, content_type=JSON), "Rechnung")
    assert c.get(one).json()["subject"] == "Standgebühr 2025"

    resp = c.post(f"{one}finalize/", {"version": neu}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] != "draft"


def test_rechnungsentwurf_ohne_fassung_wie_bisher(c, club, base, setup):
    m = make_member(club, "Erika", "Muster")
    inv = _entwurf(c, base, m)
    one = f"{base}/invoices/{inv['id']}/"
    assert c.patch(one, {"subject": "Neu"}, content_type=JSON).status_code == 200
    assert c.delete(one).status_code == 204


# --- Geschäftspartner ---------------------------------------------------------------------


def test_geschaeftspartner_und_vereinbarung_veraltete_fassung(c, club, base, setup):
    root = f"{base}/partners/"
    made = c.post(root, {"details": {"name": "Getränke Beispiel GmbH"}}, content_type=JSON)
    assert made.status_code == 201, made.json()
    partner = made.json()
    one = f"{root}{partner['id']}/"

    resp = c.patch(
        one, {"notes": "Liefert freitags", "version": partner["version"]}, content_type=JSON
    )
    assert resp.status_code == 200, resp.content
    _stale(c.patch(one, {"notes": "Anders", "version": partner["version"]}, content_type=JSON))

    made = c.post(
        f"{one}agreements/",
        {
            "title": "Bandenwerbung",
            "start": "2026-01-01",
            "end": "2026-12-31",
            "amount": "300.00",
            "benefits": ["banner"],
            "tax_kind": "advertising",
        },
        content_type=JSON,
    )
    assert made.status_code == 201, made.json()
    agreement = made.json()
    a_url = f"{one}agreements/{agreement['id']}/"
    resp = c.patch(
        a_url, {"title": "Bande Nord", "version": agreement["version"]}, content_type=JSON
    )
    assert resp.status_code == 200, resp.content
    _stale(
        c.patch(a_url, {"title": "Bande Süd", "version": agreement["version"]}, content_type=JSON)
    )
    _stale(c.delete(a_url, {"version": agreement["version"]}, content_type=JSON))
    assert c.get(f"{one}agreements/").json()[0]["title"] == "Bande Nord"
