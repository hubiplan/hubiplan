"""Gleichzeitiges Bearbeiten: Mitgliedsdaten, Termine und Buchungen tragen eine Fassung
(core/versioning.py). Wer mit einer veralteten Fassung speichert oder löscht, bekommt 409
statt den fremden Stand zu überschreiben. Ohne Fassung (ältere App) bleibt es wie bisher.
Erfundene Daten."""

import datetime

import pytest
from django.utils import timezone

from audit.models import AuditEntry
from core.tenancy import rls_bypass, tenant_context
from events.models import Event
from finance.models import Account, Booking
from members.models import Membership

from .factories import make_member

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["members", "events", "finance"]
    club.save()
    return club


@pytest.fixture
def c(api, board_a):
    return api(board_a)


def _stale(resp, wort):
    assert resp.status_code == 409, resp.content
    detail = resp.json()["detail"]
    assert wort in detail and "inzwischen geändert. Bitte neu laden." in detail


# --- Mitgliedsdaten -----------------------------------------------------------------------


def test_mitglied_veraltete_fassung_wird_abgelehnt(c, club):
    m = make_member(club, "Erika", "Muster")
    url = f"/api/orgs/{club.pk}/members/{m.pk}/"
    geladen = c.get(url).json()
    assert geladen["version"] == m.version

    # Erste Person speichert: Fassung zählt hoch
    resp = c.patch(url, {"city": "Musterdorf", "version": geladen["version"]}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > geladen["version"]

    # Zweite Person hat noch den alten Stand offen
    resp = c.patch(url, {"phone": "01234 5678", "version": geladen["version"]}, content_type=JSON)
    _stale(resp, "Mitgliedsdaten")
    assert c.get(url).json()["contact"]["phone"] == ""

    # Nach dem Neuladen klappt es
    resp = c.patch(url, {"phone": "01234 5678", "version": neu}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["contact"]["city"] == "Musterdorf"


def test_mitglied_ohne_fassung_wie_bisher_und_unsinn_abgelehnt(c, club):
    m = make_member(club, "Erika", "Muster")
    url = f"/api/orgs/{club.pk}/members/{m.pk}/"
    assert c.patch(url, {"city": "Musterdorf"}, content_type=JSON).status_code == 200
    assert c.patch(url, {"city": "Musterheim"}, content_type=JSON).status_code == 200
    for unsinn in (True, "abc", None, 0):
        resp = c.patch(url, {"city": "Anderswo", "version": unsinn}, content_type=JSON)
        _stale(resp, "Mitgliedsdaten")


def test_mitglied_fassung_steht_nicht_im_protokoll(c, club):
    m = make_member(club, "Erika", "Muster")
    url = f"/api/orgs/{club.pk}/members/{m.pk}/"
    assert c.patch(url, {"city": "Musterdorf", "version": 1}, content_type=JSON).status_code == 200
    with rls_bypass():
        eintraege = AuditEntry.objects.filter(organization=club, action="update")
        assert eintraege.exists()
        assert not any("Fassung" in (e.changes or {}) for e in eintraege)


def test_rueckgaengig_setzt_die_fassung_nicht_zurueck(c, club):
    """Sonst gälte nach „Rückgängig“ eine alte Fassung wieder, obwohl der Inhalt anders ist."""
    m = make_member(club, "Erika", "Muster")
    url = f"/api/orgs/{club.pk}/members/{m.pk}/"
    resp = c.patch(url, {"club_number": "M-77", "version": 1}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    nach_aendern = resp.json()["version"]
    paket = resp.headers["X-Change-Set"]
    resp = c.post(f"/api/orgs/{club.pk}/changes/{paket}/undo/", {}, content_type=JSON)
    assert resp.status_code < 300, resp.content
    stand = c.get(url).json()
    assert stand["club_number"] != "M-77"
    assert stand["version"] > nach_aendern


# --- Termine ------------------------------------------------------------------------------


def _termin(c, club, **data):
    resp = c.post(
        f"/api/orgs/{club.pk}/events/",
        {
            "title": "Sommerfest",
            "starts_at": "2027-06-12T14:00:00",
            "ends_at": "2027-06-12T18:00:00",
            "visibility": "members",
            **data,
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_termin_veraltete_fassung_wird_abgelehnt(c, club):
    termin = _termin(c, club)
    url = f"/api/orgs/{club.pk}/events/{termin['id']}/"
    assert termin["version"] == 1

    resp = c.patch(url, {"location": "Festplatz", "version": 1}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > 1

    resp = c.patch(url, {"title": "Herbstfest", "version": 1}, content_type=JSON)
    _stale(resp, "Termin")
    stand = c.get(url).json()
    assert stand["title"] == "Sommerfest" and stand["location"] == "Festplatz"

    resp = c.patch(url, {"title": "Herbstfest", "version": neu}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["location"] == "Festplatz"


def test_termin_loeschen_mit_veralteter_fassung(c, club):
    termin = _termin(c, club)
    url = f"/api/orgs/{club.pk}/events/{termin['id']}/"
    neu = c.patch(url, {"location": "Festplatz"}, content_type=JSON).json()["version"]
    _stale(c.delete(url, {"version": 1}, content_type=JSON), "Termin")
    assert Event.objects.filter(pk=termin["id"]).exists()
    assert c.delete(url, {"version": neu}, content_type=JSON).status_code == 204


def test_termin_ohne_fassung_wie_bisher(c, club):
    termin = _termin(c, club)
    url = f"/api/orgs/{club.pk}/events/{termin['id']}/"
    assert c.patch(url, {"location": "Festplatz"}, content_type=JSON).status_code == 200
    assert c.patch(url, {"location": "Schützenhaus"}, content_type=JSON).status_code == 200
    assert c.delete(url).status_code == 204


# --- Buchungen im Kassenbuch --------------------------------------------------------------


@pytest.fixture
def buchung(club):
    heute = timezone.localdate()
    with tenant_context(club.pk):
        konto = Account.objects.create(
            organization=club, name="Kasse", kind="cash", opening_date=datetime.date(2020, 1, 1)
        )
        return Booking.objects.create(
            organization=club,
            account=konto,
            year=club.fiscal_year_of(heute),
            number=1,
            date=heute,
            kind="income",
            amount="10.00",
            text="Spende Erika Muster",
        )


def test_buchung_veraltete_fassung_wird_abgelehnt(c, club, buchung):
    url = f"/api/orgs/{club.pk}/finance/bookings/{buchung.pk}/"
    geladen = c.get(url).json()
    assert geladen["version"] == 1

    resp = c.patch(url, {"text": "Spende Sommerfest", "version": 1}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > 1

    resp = c.patch(url, {"amount": "12.00", "version": 1}, content_type=JSON)
    _stale(resp, "Buchung")
    stand = c.get(url).json()
    assert stand["amount"] == "10.00" and stand["text"] == "Spende Sommerfest"

    resp = c.patch(url, {"amount": "12.00", "version": neu}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["text"] == "Spende Sommerfest"


def test_buchung_storno_und_loeschen_mit_veralteter_fassung(c, club, buchung):
    url = f"/api/orgs/{club.pk}/finance/bookings/{buchung.pk}/"
    neu = c.patch(url, {"text": "Spende Sommerfest"}, content_type=JSON).json()["version"]
    resp = c.post(f"{url}storno/", {"reason": "falsch erfasst", "version": 1}, content_type=JSON)
    _stale(resp, "Buchung")
    _stale(c.delete(url, {"version": 1}, content_type=JSON), "Buchung")
    with tenant_context(club.pk):
        assert Booking.objects.filter(organization=club).count() == 1
    assert c.delete(url, {"version": neu}, content_type=JSON).status_code == 204


def test_buchung_ohne_fassung_wie_bisher(c, club, buchung):
    url = f"/api/orgs/{club.pk}/finance/bookings/{buchung.pk}/"
    assert c.patch(url, {"text": "Spende A"}, content_type=JSON).status_code == 200
    assert c.patch(url, {"text": "Spende B"}, content_type=JSON).status_code == 200
    assert c.delete(url).status_code == 204


# --- Fassung selbst -----------------------------------------------------------------------


def test_jedes_speichern_zaehlt_hoch_auch_mit_update_fields(club):
    m = make_member(club, "Erika", "Muster")
    with rls_bypass(), tenant_context(club.pk):
        m = Membership.objects.get(pk=m.pk)
        start = m.version
        m.club_number = "M-1"
        m.save(update_fields=["club_number"])
        m.save()
        assert Membership.objects.get(pk=m.pk).version == start + 2
