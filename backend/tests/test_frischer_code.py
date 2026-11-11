"""Gesamtaudit 10.11., Frage 1: Plattform nur mit 2FA, frischer Code für heikle Aktionen.

Erfundene Daten. Die Sofortpflicht und die frische Bestätigung sind in conftest.py für alle
anderen Tests gelockert und werden hier eingeschaltet.
"""

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from access.catalog import FINANCE_VIEW
from access.models import Role
from accounts import step_up
from accounts.mfa_policy import status

from .factories import PASSWORD, give_role, make_user
from .test_auth import totp_code

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def streng(settings):
    settings.MFA_PLATFORM_GRACE = False
    settings.MFA_STEP_UP = True
    settings.MFA_TOTP_TOLERANCE = 1


def mit_2fa(user) -> str:
    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    user._has_mfa = None
    return secret


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        email="plattform@example.org", password=PASSWORD
    )


# --- Plattform-Verwaltung ohne Frist ---


def test_plattform_ruht_sofort_ohne_2fa(api, admin):
    resp = api(admin).get("/api/platform/orgs/")
    assert resp.status_code == 403
    assert status(admin).get("mfa_platform") is True
    # Mein Konto bleibt erreichbar, damit die 2FA eingerichtet werden kann
    assert api(admin).get("/api/me/").status_code == 200

    mit_2fa(admin)
    assert api(admin).get("/api/platform/orgs/").status_code == 200
    assert status(admin) == {}


def test_plattformrolle_ohne_2fa_ruht_ebenfalls(api, orgs):
    from access.catalog import PLATFORM_MANAGE
    from organizations.models import Organization

    user = make_user("betrieb@example.org")
    give_role(user, Organization.platform(), [PLATFORM_MANAGE], name="Betrieb")
    assert api(user).get("/api/platform/orgs/").status_code == 403
    assert status(user)["mfa_platform"] is True


def test_vorstand_behaelt_frist(api, orgs, board_a):
    # Vereinsrechte gehen in der Frist weiter, die Frist ist sichtbar
    resp = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/members/")
    assert resp.status_code == 200
    board_a.refresh_from_db()
    info = status(board_a)
    assert info["mfa_required_by"] and info["mfa_overdue"] is False
    assert "mfa_platform" not in info


# --- Frische Bestätigung ---


def export(client, org):
    return client.post(
        f"/api/orgs/{org.pk}/datatransfer/exports/", {"kind": "organization"}, content_type=JSON
    )


def test_export_ohne_2fa_mit_passwort_bestaetigen(api, orgs, board_a):
    c = api(board_a)
    resp = export(c, orgs["a"])
    assert resp.status_code == 403
    assert resp.json()["step_up"] == "password"
    assert c.get("/api/me/confirm/").json() == {
        "step_up": "password",
        "fresh": False,
        "passkey": False,
    }

    assert c.post("/api/me/confirm/", {"password": "falsch"}, content_type=JSON).status_code == 403
    assert export(c, orgs["a"]).status_code == 403
    assert c.post("/api/me/confirm/", {"password": PASSWORD}, content_type=JSON).status_code == 200
    assert export(c, orgs["a"]).status_code == 201


def test_export_mit_2fa_braucht_code(api, orgs, board_a):
    secret = mit_2fa(board_a)
    c = api(board_a)
    resp = export(c, orgs["a"])
    assert resp.status_code == 403 and resp.json()["step_up"] == "code"
    # Das Passwort genügt dann nicht
    assert c.post("/api/me/confirm/", {"password": PASSWORD}, content_type=JSON).status_code == 403
    resp = c.post("/api/me/confirm/", {"code": totp_code(secret)}, content_type=JSON)
    assert resp.status_code == 200
    assert export(c, orgs["a"]).status_code == 201


def test_bestaetigung_veraltet(api, orgs, board_a, monkeypatch):
    c = api(board_a)
    assert c.post("/api/me/confirm/", {"password": PASSWORD}, content_type=JSON).status_code == 200
    monkeypatch.setattr(step_up, "FRESH_SECONDS", -1)
    assert export(c, orgs["a"]).status_code == 403


def test_bestaetigen_gedrosselt(api, board_a):
    c = api(board_a)
    for _ in range(step_up.RATE[0]):
        c.post("/api/me/confirm/", {"password": "falsch"}, content_type=JSON)
    resp = c.post("/api/me/confirm/", {"password": PASSWORD}, content_type=JSON)
    assert resp.status_code == 429


def test_rollen_vergeben_braucht_bestaetigung(api, orgs, board_a):
    org = orgs["a"]
    role = Role.objects.get(organization=org, name="Vorstand")
    c = api(board_a)
    data = {"email": "neu@example.org", "role": role.pk}
    resp = c.post(f"/api/orgs/{org.pk}/assignments/", data, content_type=JSON)
    assert resp.status_code == 403 and resp.json()["step_up"] == "password"

    # Rechte einer Rolle erweitern ebenso, Umbenennen nicht
    other = Role.objects.create(organization=org, name="Kasse", permissions=[])
    url = f"/api/orgs/{org.pk}/roles/{other.pk}/"
    assert c.patch(url, {"name": "Kassenteam"}, content_type=JSON).status_code == 200
    resp = c.patch(url, {"permissions": [FINANCE_VIEW]}, content_type=JSON)
    assert resp.status_code == 403 and resp.json()["step_up"]

    c.post("/api/me/confirm/", {"password": PASSWORD}, content_type=JSON)
    resp = c.post(f"/api/orgs/{org.pk}/assignments/", data, content_type=JSON)
    assert resp.status_code == 201, resp.json()


def test_app_koppeln_braucht_bestaetigung(api, board_a):
    resp = api(board_a).post("/api/app/v1/pairing/")
    assert resp.status_code == 403 and resp.json()["step_up"] == "password"


def test_verein_endgueltig_loeschen_braucht_code(api, admin, orgs):
    secret = mit_2fa(admin)
    c = api(admin)
    org = orgs["c"]
    # Zweistufig (F02): vorgemerkt, Wartezeit abgelaufen, keine Finanzdaten
    import datetime

    from django.utils import timezone

    from organizations.models import Organization

    Organization.objects.filter(pk=org.pk).update(
        is_active=False, erase_requested_at=timezone.now() - datetime.timedelta(days=60)
    )
    url = f"/api/platform/orgs/{org.pk}/erase/"
    resp = c.post(url, {"confirmation": org.name}, content_type=JSON)
    assert resp.status_code == 403 and resp.json()["step_up"] == "code"
    c.post("/api/me/confirm/", {"code": totp_code(secret)}, content_type=JSON)
    assert c.post(url, {"confirmation": org.name}, content_type=JSON).status_code == 204


def test_mitglied_endgueltig_loeschen_braucht_bestaetigung(api, orgs, board_a):
    org = orgs["a"]
    resp = api(board_a).post(f"/api/orgs/{org.pk}/members/999999/erase/")
    assert resp.status_code == 403 and resp.json()["step_up"] == "password"
