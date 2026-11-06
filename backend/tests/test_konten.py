"""Einstellungen › Konten: Übersicht, Filterfelder und Sammelversand (Rollen-Vorschlag R4)."""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.utils import timezone

from accounts.models import User

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/accounts/{rest}"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.member_portal_enabled = True
    club.save()
    return club


def test_konten_mit_rollen_und_mitgliederbereich(api, club, board_a):
    kasse = User.objects.create_user(email="kasse@example.org")
    kasse.date_joined = timezone.now() - datetime.timedelta(days=30)
    kasse.save()
    give_role(kasse, club, ["finance.edit"], name="Kassierer")
    erika = make_member(club, "Erika", "Muster", "erika@example.org")
    c = api(board_a)
    assert c.post(f"/api/orgs/{club.pk}/members/{erika.pk}/access/").status_code == 200

    rows = {r["email"]: r for r in c.get(url(club)).json()}
    assert set(rows) >= {"kasse@example.org", "erika@example.org", "vorstand-a@example.org"}
    assert rows["kasse@example.org"]["roles"] == ["Kassierer"]
    assert rows["kasse@example.org"]["rights"] is True
    assert rows["kasse@example.org"]["invitation_expired"] is True
    assert rows["kasse@example.org"]["last_login"] is None
    assert rows["erika@example.org"]["member_area"] is True
    assert rows["erika@example.org"]["roles"] == []
    assert rows["erika@example.org"]["name"] == "Erika Muster"
    assert rows["erika@example.org"]["membership"] == erika.pk


def test_sammelversand(api, club, board_a):
    kasse = User.objects.create_user(email="kasse2@example.org")
    give_role(kasse, club, ["finance.edit"], name="Kassierer")
    erika = make_member(club, "Erika", "Muster", "erika2@example.org")
    c = api(board_a)
    c.post(f"/api/orgs/{club.pk}/members/{erika.pk}/access/")
    erika_user = User.objects.get(email="erika2@example.org")
    mail.outbox.clear()

    resp = c.post(
        url(club, "resend/"),
        {"users": [kasse.pk, erika_user.pk, board_a.pk]},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    # Der Vorstand hat schon ein Passwort: übersprungen
    assert resp.json() == {
        "sent": ["kasse2@example.org", "erika2@example.org"],
        "skipped": ["vorstand-a@example.org"],
    }
    assert sorted(m.to[0] for m in mail.outbox) == ["erika2@example.org", "kasse2@example.org"]


def test_nur_mitgliederkonten_ohne_rollenrecht(api, club, board_a):
    """Wer nur Konten der Mitglieder verwaltet, sieht keine Vorstandskonten."""
    pfleger = make_user("pflege@example.org")
    give_role(pfleger, club, ["logins.edit"], name="Zugangspflege")
    erika = make_member(club, "Erika", "Muster", "erika3@example.org")
    api(board_a).post(f"/api/orgs/{club.pk}/members/{erika.pk}/access/")
    c = api(pfleger)
    emails = [r["email"] for r in c.get(url(club)).json()]
    assert emails == ["erika3@example.org"]
    resp = c.post(url(club, "resend/"), {"users": [board_a.pk]}, content_type=JSON)
    assert resp.status_code == 403


def test_ohne_recht_kein_zugriff(api, club):
    other = make_user("anderer@example.org")
    give_role(other, club, ["events.view"], name="Termine")
    assert api(other).get(url(club)).status_code == 403
