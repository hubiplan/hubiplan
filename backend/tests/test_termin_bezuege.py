"""Termin als Mittelpunkt (Menüprüfung 2, N-02): Versammlung, Dienstpläne und Belegungen
am Termin, je nach Modul und Recht."""

import datetime

import pytest
from django.utils import timezone

from core.tenancy import tenant_context

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def test_bezuege_am_termin(api, orgs, board_a):
    from bookings.models import Booking
    from helpers.models import HelperPlan
    from materials.models import MaterialItem

    org = orgs["a"]
    org.enabled_modules = sorted(
        {*org.enabled_modules, "events", "meetings", "helpers", "bookings", "infrastructure"}
    )
    org.save()
    c = api(board_a)
    base = f"/api/orgs/{org.pk}/meetings/"
    kind = next(k for k in c.get(base + "kinds/").json() if k["name"] == "Jahreshauptversammlung")
    start = timezone.now() + datetime.timedelta(days=10)
    resp = c.post(
        base,
        {
            "kind": kind["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + datetime.timedelta(hours=2)).isoformat(),
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.content
    meeting = resp.json()
    with tenant_context(org.pk):
        from meetings.models import Meeting

        event = Meeting.objects.get(pk=meeting["id"]).event
        plan = HelperPlan.objects.create(organization=org, title="Saaldienst", event=event)
        house = MaterialItem.objects.create(
            organization=org,
            kind="facility",
            title="Schützenhaus",
            location_kind="address",
            address={"street": "Musterweg 1", "postal_code": "12345", "city": "Musterstadt"},
            facility_type="building",
            booking_rules={"enabled": True},
        )
        Booking.objects.create(
            organization=org,
            item=house,
            title="JHV",
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            event=event,
            status="confirmed",
        )
        Booking.objects.create(
            organization=org,
            item=house,
            title="Abgesagt",
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            event=event,
            status="cancelled",
        )

    detail_url = f"/api/orgs/{org.pk}/events/{event.pk}/"
    data = c.get(detail_url).json()
    assert data["meeting"]["id"] == meeting["id"]
    assert [(p["id"], p["title"]) for p in data["helper_plans"]] == [(plan.pk, "Saaldienst")]
    assert data["can_create_helper_plan"] is True
    assert [b["item"] for b in data["bookings"]] == ["Schützenhaus"]

    # Nur Termine und Versammlungen lesen: keine Dienstpläne, keine Belegungen
    leser = make_user("beisitz@example.org")
    give_role(leser, org, permissions=["events.view", "meetings.view"], name="Beisitz")
    data = api(leser).get(detail_url).json()
    assert data["meeting"]["id"] == meeting["id"]
    assert "helper_plans" not in data
    assert "bookings" not in data
