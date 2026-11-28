"""App für Konten ohne Mitgliederbereich: verbinden mit Rolle, nur die Verwaltung sichtbar."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import datetime

import pytest
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import rls_bypass
from devices.models import Device
from portal.models import PortalAccess

from .factories import give_role, make_user
from .test_app_devices import APP, app, pair, pairing_code
from .test_m12_events import (  # noqa: F401  (Fixtures)
    cal,
    member_with_access,
    org_base,
)

pytestmark = pytest.mark.django_db
ADMIN = f"{APP}admin/"


@pytest.fixture
def cashier(cal):
    """Kassierer mit Rolle in Verein a, selbst kein Mitglied, kein Mitgliederbereich."""
    user = make_user("kasse@example.org")
    role = give_role(user, cal["a"], name="Kasse")
    return user, role


def test_verbinden_mit_rolle_ohne_mitgliederbereich(cashier, api, cal):
    user, _ = cashier
    assert api(user).get("/api/me/contexts/").json()["app"] is True
    resp = pair(pairing_code(api(user)))
    assert resp.status_code == 201, resp.json()
    client = app(resp.json()["token"])
    me = client.get(f"{APP}me/").json()
    assert me["portal"] == [] and me["admin"] is True
    data = client.get(ADMIN).json()
    assert [u["id"] for u in data["units"]] == [cal["a"].pk]
    assert data["unlocked"] is False
    # Geräteliste im Browser und in der App
    assert len(api(user).get(f"{APP}devices/").json()) == 1


def test_geraeteschluessel_allein_liest_nichts(cashier, api, cal):
    user, _ = cashier
    token = pair(pairing_code(api(user))).json()["token"]
    # Die Verwaltung verlangt den Vorstandsschlüssel, der Geräteschlüssel reicht nie
    resp = app(token).get(f"{ADMIN}u/{cal['a'].pk}/members/")
    assert resp.status_code in (401, 403)


def test_ohne_rolle_und_ohne_mitgliederbereich_nicht(api):
    user = make_user("niemand@example.org")
    assert api(user).get("/api/me/contexts/").json()["app"] is False
    assert api(user).post(f"{APP}pairing/").status_code == 400


def test_mitglied_meldet_admin_falsch(cal, api):
    _, user, _ = member_with_access(cal["a"], "Otto")
    token = pair(pairing_code(api(user))).json()["token"]
    me = app(token).get(f"{APP}me/").json()
    assert len(me["portal"]) == 1 and me["admin"] is False


def test_rolle_entzogen_meldet_geraete_ab(cashier, api, django_capture_on_commit_callbacks):
    user, role = cashier
    pair(pairing_code(api(user)))
    assert Device.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    with django_capture_on_commit_callbacks(execute=True), rls_bypass():
        RoleAssignment.objects.filter(pk=role.pk).first().delete()
    assert not Device.objects.filter(user=user, revoked_at__isnull=True).exists()


def test_rolle_beendet_meldet_geraete_ab(cashier, api, django_capture_on_commit_callbacks):
    user, role = cashier
    pair(pairing_code(api(user)))
    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    with django_capture_on_commit_callbacks(execute=True), rls_bypass():
        entry = RoleAssignment.objects.get(pk=role.pk)
        entry.valid_from = yesterday - datetime.timedelta(days=30)
        entry.valid_until = yesterday
        entry.save()
    assert not Device.objects.filter(user=user, revoked_at__isnull=True).exists()


def test_zugang_geloescht_rolle_bleibt(cal, api, django_capture_on_commit_callbacks):
    """Vorstand, der auch Mitglied ist: Endet der Mitgliederbereich, bleibt die App."""
    _, user, access = member_with_access(cal["a"], "Vera")
    give_role(user, cal["a"])
    pair(pairing_code(api(user)))
    with django_capture_on_commit_callbacks(execute=True), rls_bypass():
        PortalAccess.objects.filter(pk=access.pk).delete()
    assert Device.objects.filter(user=user, revoked_at__isnull=True).count() == 1


def test_zweite_rolle_haelt_geraete(cashier, api, cal, django_capture_on_commit_callbacks):
    user, role = cashier
    give_role(user, cal["b"], name="Kasse")
    pair(pairing_code(api(user)))
    with django_capture_on_commit_callbacks(execute=True), rls_bypass():
        RoleAssignment.objects.filter(pk=role.pk).first().delete()
    assert Device.objects.filter(user=user, revoked_at__isnull=True).count() == 1


def test_funktion_gemeldet():
    from django.test import Client

    assert "app-nur-verwaltung" in Client().get(f"{APP}instance/").json()["features"]
