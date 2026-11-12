"""Kündigung durch das Mitglied im Mitgliederbereich."""

import datetime

import pytest
from django.core import mail

from members.models import MembershipPeriod
from portal import cancellation
from portal.models import CancellationRequest, PortalAccess

from .factories import make_member

pytestmark = pytest.mark.django_db
JSON = "application/json"
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.member_portal_enabled = True
    club.member_cancellation_enabled = True
    club.cancellation_notice_months = 3
    club.cancellation_period_end = "year"
    club.save()
    return club


@pytest.fixture
def heute(monkeypatch):
    monkeypatch.setattr(cancellation, "today", lambda: D(2026, 11, 12))
    return D(2026, 11, 12)


@pytest.fixture
def mitglied(club, api, board_a):
    m = make_member(club, "Erika", "Muster", "erika@example.org")
    api(board_a).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/")
    access = PortalAccess.objects.get()
    return m, access, api(access.user)


@pytest.mark.parametrize(
    ("monate", "termin", "eingang", "erwartet"),
    [
        (3, "year", D(2026, 11, 12), D(2027, 12, 31)),
        (3, "year", D(2026, 9, 30), D(2026, 12, 31)),
        (3, "year", D(2026, 10, 1), D(2027, 12, 31)),
        (0, "year", D(2026, 11, 12), D(2026, 12, 31)),
        (1, "month", D(2026, 1, 31), D(2026, 2, 28)),
        (3, "quarter", D(2026, 11, 12), D(2027, 3, 31)),
        (6, "half_year", D(2026, 1, 1), D(2026, 12, 31)),
        (0, "any", D(2026, 11, 12), D(2026, 11, 12)),
        (2, "any", D(2026, 11, 12), D(2027, 1, 12)),
    ],
)
def test_fruehester_austritt(club, monate, termin, eingang, erwartet):
    club.cancellation_notice_months = monate
    club.cancellation_period_end = termin
    assert cancellation.earliest_exit(club, eingang) == erwartet


def test_geschaeftsjahr_zaehlt(club):
    """Jahresende heißt Ende des Geschäftsjahres (hier 1. Juli bis 30. Juni)."""
    club.fiscal_start_month = 7
    club.cancellation_notice_months = 3
    club.cancellation_period_end = "year"
    assert cancellation.earliest_exit(club, D(2026, 3, 1)) == D(2026, 6, 30)
    assert cancellation.earliest_exit(club, D(2026, 4, 1)) == D(2027, 6, 30)


def test_kuendigen_und_bestaetigen(
    club, mitglied, heute, api, board_a, django_capture_on_commit_callbacks
):
    m, access, member = mitglied
    detail = member.get(f"/api/portal/{access.pk}/").json()["cancellation"]
    assert detail["enabled"] and detail["possible"]
    assert detail["earliest_date"] == "2027-12-31"
    assert "3 Monaten" in detail["rule"]

    # ohne Bestätigung nicht
    resp = member.post(
        f"/api/portal/{access.pk}/cancellation/", {"confirm": False}, content_type=JSON
    )
    assert resp.status_code == 400
    # zu früh nicht
    resp = member.post(
        f"/api/portal/{access.pk}/cancellation/",
        {"confirm": True, "exit_date": "2026-12-31"},
        content_type=JSON,
    )
    assert resp.status_code == 400 and "exit_date" in resp.json()

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = member.post(
            f"/api/portal/{access.pk}/cancellation/",
            {"confirm": True, "message": "Umzug"},
            content_type=JSON,
        )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["exit_date"] == "2027-12-31"
    assert any("Kündigung eingegangen" in x.subject for x in mail.outbox)
    # zweite Kündigung nicht, solange eine offen ist
    resp = member.post(
        f"/api/portal/{access.pk}/cancellation/", {"confirm": True}, content_type=JSON
    )
    assert resp.status_code == 400
    assert member.get(f"/api/portal/{access.pk}/").json()["cancellation"]["possible"] is False

    board = api(board_a)
    tasks = board.get(f"/api/orgs/{club.pk}/open-tasks/").json()
    assert any(t["kind"] == "cancellation" for t in tasks["items"])
    pending = board.get(f"/api/orgs/{club.pk}/cancellations/").json()
    assert len(pending) == 1 and pending[0]["member_name"] == "Erika Muster"

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = board.post(
            f"/api/orgs/{club.pk}/cancellations/{pending[0]['id']}/decide/",
            {"accept": True, "response": "Schade!"},
            content_type=JSON,
        )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "accepted"
    period = MembershipPeriod.objects.get(membership=m)
    assert period.exit_date == D(2027, 12, 31) and period.exit_reason == "exit"
    assert any("Austrittsbestätigung" in x.subject and "Schade!" in x.body for x in mail.outbox)
    # bis zum Austritt aktiv, Kündigung nicht mehr möglich
    detail = member.get(f"/api/portal/{access.pk}/").json()
    assert detail["status"] == "active"
    assert detail["cancellation"]["possible"] is False
    assert detail["cancellation"]["planned_exit"] == "2027-12-31"
    # schon bearbeitet
    resp = board.post(
        f"/api/orgs/{club.pk}/cancellations/{pending[0]['id']}/decide/",
        {"accept": False},
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_spaeteres_datum_und_zuruecknehmen(club, mitglied, heute):
    m, access, member = mitglied
    resp = member.post(
        f"/api/portal/{access.pk}/cancellation/",
        {"confirm": True, "exit_date": "2028-06-30"},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    pk = resp.json()["id"]
    resp = member.delete(f"/api/portal/{access.pk}/cancellation/{pk}/")
    assert resp.status_code == 200 and resp.json()["status"] == "withdrawn"
    assert MembershipPeriod.objects.get(membership=m).exit_date is None
    # nach dem Zurücknehmen wieder möglich
    assert member.get(f"/api/portal/{access.pk}/").json()["cancellation"]["possible"] is True


def test_ablehnen_und_datum_anpassen(club, mitglied, heute, api, board_a):
    m, access, member = mitglied
    member.post(f"/api/portal/{access.pk}/cancellation/", {"confirm": True}, content_type=JSON)
    c = CancellationRequest.objects.get()
    resp = api(board_a).post(
        f"/api/orgs/{club.pk}/cancellations/{c.pk}/decide/",
        {"accept": False, "response": "Bitte schriftlich"},
        content_type=JSON,
    )
    assert resp.json()["status"] == "rejected"
    assert MembershipPeriod.objects.get(membership=m).exit_date is None

    member.post(f"/api/portal/{access.pk}/cancellation/", {"confirm": True}, content_type=JSON)
    c = CancellationRequest.objects.get(status="pending")
    resp = api(board_a).post(
        f"/api/orgs/{club.pk}/cancellations/{c.pk}/decide/",
        {"accept": True, "exit_date": "2027-06-30"},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    assert MembershipPeriod.objects.get(membership=m).exit_date == D(2027, 6, 30)


def test_ausgeschaltet(club, mitglied, heute):
    club.member_cancellation_enabled = False
    club.save()
    m, access, member = mitglied
    assert member.get(f"/api/portal/{access.pk}/").json()["cancellation"]["enabled"] is False
    resp = member.post(
        f"/api/portal/{access.pk}/cancellation/", {"confirm": True}, content_type=JSON
    )
    assert resp.status_code == 400
    assert not CancellationRequest.objects.exists()


def test_fremdes_mitglied_und_fremder_verein(club, orgs, mitglied, heute, api, board_a):
    m, access, member = mitglied
    member.post(f"/api/portal/{access.pk}/cancellation/", {"confirm": True}, content_type=JSON)
    c = CancellationRequest.objects.get()
    # andere Zugangsnummer: nicht gefunden
    resp = member.post(
        f"/api/portal/{access.pk + 99}/cancellation/", {"confirm": True}, content_type=JSON
    )
    assert resp.status_code == 404
    # Vorstand eines anderen Vereins sieht und entscheidet nichts
    from .factories import give_role, make_user

    fremd = make_user("vorstand-b@example.org")
    give_role(fremd, orgs["b"])
    assert api(fremd).get(f"/api/orgs/{orgs['b'].pk}/cancellations/").json() == []
    resp = api(fremd).post(
        f"/api/orgs/{orgs['b'].pk}/cancellations/{c.pk}/decide/",
        {"accept": True},
        content_type=JSON,
    )
    assert resp.status_code == 404


def test_einstellungen_speichern(club, api, board_a):
    resp = api(board_a).patch(
        f"/api/orgs/{club.pk}/member-settings/",
        {"cancellation_notice_months": 1, "cancellation_period_end": "quarter"},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    club.refresh_from_db()
    assert club.cancellation_period_end == "quarter"
