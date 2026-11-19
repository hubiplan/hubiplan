"""Belegung für ein Mitglied: Zuordnung, Akte, Mitgliederbereich und Auskunft."""

import datetime

import pytest
from django.utils import timezone

from bookings.models import Booking

from .factories import give_role, make_member, make_user
from .test_buchungen import JSON, at, book, setup  # noqa: F401  (Fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mitglied(setup, api):  # noqa: F811
    s = setup
    org = s["org"]
    admin = make_user("vorstand@example.org")
    give_role(
        admin,
        org,
        permissions=["infrastructure.edit", "material.edit", "members.view"],
        name="Schriftführung",
    )
    s["vorstand"] = api(admin)
    s["membership"] = make_member(org, "Erika", "Beispiel", email="erika@example.org")
    return s


def test_buchung_fuer_ein_mitglied(mitglied):
    s = mitglied
    choices = s["vorstand"].get(s["url"] + "choices/?kind=member&q=beisp").json()
    assert choices["items"] == [{"id": s["membership"].pk, "title": "Beispiel, Erika"}]
    response = book(
        s["vorstand"], s["url"], s["hall"], at(2, 18), at(2, 20), member=s["membership"].pk
    )
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["member"] == s["membership"].pk
    assert data["member_name"] == "Beispiel, Erika"
    listing = s["vorstand"].get(s["url"] + f"?start={timezone.localdate()}").json()
    assert {r["member_name"] for r in listing["occurrences"]} == {"Beispiel, Erika"}
    akte = s["vorstand"].get(f"{s['url']}member/{s['membership'].pk}/").json()
    assert [b["id"] for b in akte["bookings"]] == [data["id"]]
    # Zuordnung wieder entfernen
    patched = s["vorstand"].patch(
        f"{s['url']}{data['id']}/",
        {"member": None, "version": data["version"]},
        content_type=JSON,
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["member"] is None
    assert Booking.objects.get(pk=data["id"]).member_id is None


def test_ohne_mitgliederrecht_keine_auswahl(mitglied):
    s = mitglied
    # Verwalter ohne „Mitglieder ansehen“ findet und wählt kein Mitglied
    assert s["admin"].get(s["url"] + "choices/?kind=member&q=beisp").json()["items"] == []
    response = book(
        s["admin"], s["url"], s["hall"], at(2, 18), at(2, 20), member=s["membership"].pk
    )
    assert response.status_code == 400
    assert s["admin"].get(f"{s['url']}member/{s['membership'].pk}/").status_code == 404
    # Wer nur buchen darf, ordnet kein Mitglied zu
    other = book(s["member"], s["url"], s["hall"], at(3, 18), at(3, 20), member=s["membership"].pk)
    assert other.status_code == 403
    plain = book(s["member"], s["url"], s["hall"], at(3, 18), at(3, 20)).json()
    assert plain["member"] is None and plain["member_name"] == ""


def test_mitgliederbereich_zeigt_zugeordnete_buchung(mitglied, api):
    from portal.models import PortalAccess

    s = mitglied
    org = s["org"]
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    s["hall"].booking_rules = {"enabled": True, "approval": True, "portal": True}
    s["hall"].save()
    user = make_user("erika@example.org")
    access = PortalAccess.objects.create(organization=org, membership=s["membership"], user=user)
    booking = book(
        s["vorstand"], s["url"], s["hall"], at(6, 10), at(6, 12), member=s["membership"].pk
    ).json()
    portal = api(user)
    url = f"/api/portal/{access.pk}/bookings/"
    data = portal.get(url + f"?start={timezone.localdate() + datetime.timedelta(days=6)}").json()
    assert [b["id"] for b in data["own"]] == [booking["id"]]
    assert [(r["title"], r["own"]) for r in data["occurrences"]] == [("Training", True)]
    # Wer sie als Verwaltung eingetragen hat, sieht sie im eigenen Mitgliederbereich nicht
    # als seine Buchung und sagt sie dort nicht ab (Gesamtaudit 19.11., F-02)
    from accounts.models import User

    admin = User.objects.get(email="vorstand@example.org")
    eigene = make_member(org, "Vera", "Vorstand", email="vorstand@example.org")
    zugang = PortalAccess.objects.create(organization=org, membership=eigene, user=admin)
    fremd = api(admin)
    eigen_url = f"/api/portal/{zugang.pk}/bookings/"
    assert fremd.get(eigen_url).json()["own"] == []
    absage = fremd.post(
        f"{eigen_url}{booking['id']}/cancel/", {"version": booking["version"]}, content_type=JSON
    )
    assert absage.status_code == 404
    assert Booking.objects.get(pk=booking["id"]).status == booking["status"]


def test_auskunft_nennt_belegungen(mitglied):
    import json

    from members import auskunft

    s = mitglied
    book(s["vorstand"], s["url"], s["hall"], at(2, 18), at(2, 20), member=s["membership"].pk)
    files = auskunft._further(s["membership"], [s["org"].pk])
    rows = json.loads(files["belegungen.json"])
    assert [(r["objekt"], r["title"]) for r in rows] == [("Saal", "Training")]
    assert not {"contact", "booked_by_id", "member_id"} & set(rows[0])
