"""Einlass vor Ort mit dem Kamera-Scanner der App (Anmeldung A6/A7). Alle Daten erfunden."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from core.tenancy import tenant_context
from registrations import tickets
from registrations.models import Participant

from .factories import give_role, make_member
from .test_app_devices import APP, app
from .test_app_verwaltung import admin_token, board  # noqa: F401
from .test_m12_events import JSON, cal  # noqa: F401
from .test_m13_rsvp import soon

pytestmark = pytest.mark.django_db
ADMIN = f"{APP}admin/u/"


def test_einlass_in_der_app(board, admin_token, cal, api):
    club = cal["a"]
    club.enabled_modules = sorted({*club.enabled_modules, "registrations"})
    club.save()
    give_role(
        board["user"],
        club,
        ["events.manage", "registrations.view", "registrations.edit"],
        name="Einlass",
    )
    browser = api(board["user"])
    org = f"/api/orgs/{club.pk}"
    event = browser.post(
        f"{org}/events/", {"title": "Sommerfest", "starts_at": soon(14)}, content_type=JSON
    ).json()
    resp = browser.put(
        f"{org}/events/{event['id']}/registration/",
        {"closes_at": soon(10), "prices": [{"name": "Alle", "steps": [{"amount": "0"}]}]},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    price = resp.json()["offer"]["prices"][0]["id"]
    anna = make_member(club, "Anna", "Beispiel")
    resp = browser.post(
        f"{org}/events/{event['id']}/registration/list/",
        {
            "name": "Anna Beispiel",
            "persons": [{"membership_id": anna.pk, "name": "", "price_id": price}],
        },
        content_type=JSON,
    )
    assert resp.status_code in (200, 201), resp.json()
    with tenant_context(club.pk):
        code = tickets.code(Participant.objects.get(membership=anna))
    c = app(admin_token)
    url = f"{ADMIN}{club.pk}/events/{event['id']}/registration/checkin/"
    listing = c.get(url).json()
    assert listing["count"] == 1 and listing["can_edit"]
    row = listing["participants"][0]
    assert row["invoice_id"] is None and row["outstanding"] == "0.00"
    assert "can_cash" in listing
    done = c.post(url, {"code": code}, content_type=JSON).json()
    assert done["result"] == "ok"
    assert c.post(url, {"code": code}, content_type=JSON).json()["result"] == "already"
