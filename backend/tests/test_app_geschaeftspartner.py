"""Android-App: Kontaktsuche bei Geschäftspartnern (Konzept geschaeftspartner.md, P5), nur lesen."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from .factories import give_role
from .test_app_devices import app
from .test_app_verwaltung_b4 import ADMIN, _private, unlocked  # noqa: F401
from .test_m12_events import JSON, cal, member_with_access  # noqa: F401

pytestmark = pytest.mark.django_db


def test_app_findet_partner_und_ansprechpartner(cal, api):
    club = cal["a"]
    club.enabled_modules = ["members", "events", "finance", "portal"]
    club.save()
    _, user, _ = member_with_access(club, "Kim")
    give_role(user, club, ["finance.view", "partners.view", "partners.edit"], name="Kassenprüfung")
    web = api(user)
    base = f"/api/orgs/{club.pk}/billing/partners/"
    made = web.post(
        base,
        {"details": {"name": "Zeltverleih Beispiel", "city": "Musterstadt"}, "roles": ["venue"]},
        content_type=JSON,
    )
    assert made.status_code == 201, made.content
    web.post(
        f"{base}{made.json()['id']}/contacts/",
        {"last_name": "Muster", "first_name": "Alex", "phone": "+49 30 123456"},
        content_type=JSON,
    )
    web.post(base, {"details": {"name": "Druckerei Beispiel"}}, content_type=JSON)
    c = app(unlocked(api, user))
    url = f"{ADMIN}u/{club.pk}/billing/partners/"
    rows = c.get(f"{url}?suche=alex").json()
    assert [r["name"] for r in rows] == ["Zeltverleih Beispiel"]
    assert rows[0]["contacts"][0]["phone"] == "+49 30 123456"
    assert len(c.get(url).json()) == 2
    # nur lesen
    assert c.post(url, {"details": {"name": "X"}}, content_type=JSON).status_code == 405
