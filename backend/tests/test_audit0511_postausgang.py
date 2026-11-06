"""Gesamtaudit 05.11. F-04: Plattform-Betreuung sieht im Postausgang nur Kopfdaten."""

import pytest

from core.tenancy import rls_bypass
from outbox import mail
from outbox.models import OutgoingMail

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _postausgang(settings):
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser("plattform@example.org", "x")


def _platform_row(api, admin, subject):
    rows = api(admin).get("/api/platform/outbox/").json()["results"]
    return next(r for r in rows if r["subject"] == subject)


def test_inhalt_nur_mit_freigabe_des_vereins(api, admin, orgs, board_a):
    club = orgs["a"]
    mail.send(
        "m@example.org",
        "Vereinsmail",
        "Geheimer Text",
        organization=club,
        attachments=[("plan.pdf", b"%PDF-1.4", "application/pdf")],
    )
    with rls_bypass():
        sent = OutgoingMail.objects.get(subject="Vereinsmail")
    row = _platform_row(api, admin, "Vereinsmail")
    assert row["content_hidden"] is True
    assert row["body"] == "" and row["to"] == "m@example.org"
    url = f"/api/platform/outbox/{sent.pk}/attachments/0/"
    assert sent.attachments
    assert api(admin).get(url).status_code == 404

    # Der Verein selbst sieht alles
    own = api(board_a).get(f"/api/orgs/{club.pk}/outbox/").json()["results"][0]
    assert own["body"].startswith("Geheimer Text") and not own["content_hidden"]

    settings_url = f"/api/orgs/{club.pk}/outbox/settings/"
    assert api(board_a).get(settings_url).json() == {"platform_content": False}
    resp = api(board_a).patch(settings_url, {"platform_content": True}, content_type=JSON)
    assert resp.status_code == 200
    row = _platform_row(api, admin, "Vereinsmail")
    assert row["content_hidden"] is False and row["body"].startswith("Geheimer Text")
    assert api(admin).get(url).status_code == 200


def test_mails_ohne_verein_bleiben_lesbar(api, admin):
    mail.send("x@example.org", "Ohne Verein", "Plattformtext")
    row = _platform_row(api, admin, "Ohne Verein")
    assert row["content_hidden"] is False and row["body"].startswith("Plattformtext")


def test_freigabe_nur_mit_bearbeitungsrecht(api, orgs):
    from .factories import give_role, make_user

    club = orgs["a"]
    reader = make_user("leser@example.org")
    give_role(reader, club, ["audit.view"], name="Protokoll")
    url = f"/api/orgs/{club.pk}/outbox/settings/"
    assert api(reader).get(url).status_code == 200
    resp = api(reader).patch(url, {"platform_content": True}, content_type=JSON)
    assert resp.status_code == 403
