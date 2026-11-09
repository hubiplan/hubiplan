"""App-Reiter „Ich“ (konzepte/app-ich.md): Rechnungen, Mandat, Versammlungen und Dokumente
des Mitgliederbereichs sind mit dem Geräteschlüssel der App erreichbar, ohne Sitzung im Browser."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from meetings.models import Meeting
from portal.models import PortalAccess

from .factories import make_member, make_user
from .test_app_devices import app, pair, pairing_code
from .test_versammlungen import JSON, new_meeting, ok, release, setup  # noqa: F401  (Fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture
def device(setup, api):
    """Mitglied mit Zugang zum Mitgliederbereich und verbundener App."""
    org = setup["org"]
    org.member_portal_enabled = True
    org.enabled_modules = sorted({*org.enabled_modules, "billing", "docs"})
    org.save(update_fields=["member_portal_enabled", "enabled_modules"])
    erika = make_member(org, "Erika", "Beispiel", email="erika@example.org")
    user = make_user("erika@example.org")
    access = PortalAccess.objects.create(organization=org, membership=erika, user=user)
    resp = pair(pairing_code(api(user)))
    assert resp.status_code == 201, resp.json()
    return app(resp.json()["token"]), access


def test_rechnungen_und_mandat_mit_geraeteschluessel(device):
    c, access = device
    data = ok(c.get(f"/api/portal/{access.pk}/invoices/"))
    assert data == {"invoices": [], "collective": []}
    mandate = ok(c.get(f"/api/portal/{access.pk}/mandate/"))
    assert mandate["mandate"] is None and "available" in mandate
    # Fremde oder fehlende Rechnung: nicht gefunden, aber angemeldet (kein 401)
    assert c.get(f"/api/portal/{access.pk}/invoices/999999/pdf/").status_code == 404


def test_versammlungen_antraege_und_protokoll_mit_geraeteschluessel(setup, device):
    c, access = device
    done = release(setup, new_meeting(setup), [{"text": "Entlastung.", "unanimous": True}])
    coming = new_meeting(setup, location="Schützenhaus")
    Meeting.objects.filter(pk=coming["id"]).update(status="invited")
    url = f"/api/portal/{access.pk}/meetings/"
    data = ok(c.get(url))
    assert [m["id"] for m in data["upcoming"]] == [coming["id"]]
    assert [m["id"] for m in data["minutes"]] == [done["id"]]
    # Antrag stellen und zurückziehen, ohne CSRF-Token (keine Sitzung im Spiel)
    mine = ok(
        c.post(
            f"{url}{coming['id']}/motions/",
            {"title": "Neue Fahne", "text": "Die alte ist verschlissen."},
            content_type=JSON,
        ),
        201,
    )
    assert [m["status"] for m in mine] == ["submitted"]
    resp = c.post(f"{url}motions/{mine[0]['id']}/withdraw/", {}, content_type=JSON)
    assert resp.status_code == 204
    assert ok(c.get(url))["upcoming"][0]["motions"][0]["status"] == "withdrawn"
    resp = c.get(f"{url}{done['id']}/minutes/")
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content).startswith(b"%PDF")


def test_dokumente_mit_geraeteschluessel(device):
    c, access = device
    data = ok(c.get(f"/api/portal/{access.pk}/documents/"))
    assert "folders" in data and data["can_manage"] is False


def test_zugang_eines_anderen_bleibt_verschlossen(setup, device):
    c, _ = device
    other = make_member(setup["org"], "Max", "Muster", email="max@example.org")
    foreign = PortalAccess.objects.create(
        organization=setup["org"], membership=other, user=make_user("max@example.org")
    )
    for path in ("invoices/", "mandate/", "meetings/", "documents/"):
        assert c.get(f"/api/portal/{foreign.pk}/{path}").status_code in (403, 404), path
