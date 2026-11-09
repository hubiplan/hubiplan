"""Termine: der Vorstand legt Termine für Untereinheiten ohne Selbstverwaltung an."""

import pytest

from events import rsvp
from events.models import Event
from organizations.models import Department

from .factories import give_role, make_user
from .test_m12_events import JSON, create, member_with_access, org_base, titles

pytestmark = pytest.mark.django_db


@pytest.fixture
def cal(orgs):
    for org in orgs.values():
        org.enabled_modules = ["members", "events"]
        org.member_portal_enabled = True
        org.department_access_enabled = True
        org.save()
    return orgs


@pytest.fixture
def board_fed(cal):
    user = make_user("vorstand-bund@example.org")
    give_role(user, cal["federation"])
    return user


@pytest.fixture
def korps(cal):
    # Von oben verwaltet (Voreinstellung), mit einer Untereinheit darunter
    korps = Department.objects.create(organization=cal["a"], name="Korps")
    zug = Department.objects.create(organization=cal["a"], name="1. Zug", parent=korps)
    return korps, zug


@pytest.fixture
def selbst(cal):
    eigen = Department.objects.create(organization=cal["a"], name="Eigenzug", self_managed=True)
    darunter = Department.objects.create(organization=cal["a"], name="Rotte", parent=eigen)
    return eigen, darunter


def units(client, org):
    resp = client.get(f"{org_base(org)}events/?from=2026-01-01&to=2026-12-31")
    assert resp.status_code == 200, resp.content
    return resp.json()["units"]


class TestAuswahl:
    def test_nur_untereinheiten_ohne_selbstverwaltung(self, cal, korps, selbst, board_a, api):
        got = units(api(board_a), cal["a"])
        assert [u["name"] for u in got] == ["Korps", "1. Zug"]
        assert got[1]["path"] == "Korps › 1. Zug" and got[1]["depth"] == 1

    def test_ohne_terminrecht_keine_auswahl(self, cal, korps, api):
        reader = make_user("leser@example.org")
        give_role(reader, cal["a"], ["events.view"], name="Leser")
        assert units(api(reader), cal["a"]) == []

    def test_dachverband_hat_keine_auswahl(self, cal, korps, board_fed, api):
        assert units(api(board_fed), cal["federation"]) == []


class TestAnlegen:
    def test_termin_fuer_untereinheit(self, cal, korps, board_a, api):
        _, zug = korps
        c = api(board_a)
        data = create(c, org_base(cal["a"]), title="Zugabend", department_id=zug.pk)
        assert data["department_id"] == zug.pk
        assert data["owner"] == "1. Zug" and data["can_edit"] is True
        ev = Event.objects.get(pk=data["id"])
        assert ev.organization == cal["a"] and ev.department == zug
        # Der Vorstand sieht und pflegt ihn im Kalender der Einheit
        assert "Zugabend" in titles(c, org_base(cal["a"]))
        resp = c.patch(
            f"{org_base(cal['a'])}events/{ev.pk}/", {"title": "Zugversammlung"}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["title"] == "Zugversammlung"

    def test_auch_interne_termine_und_ohne_weitergabe(self, cal, korps, board_a, api):
        korps_unit, _ = korps
        korps_unit.events_share_up = False
        korps_unit.save()
        c = api(board_a)
        create(c, org_base(cal["a"]), title="Korpsrat", department_id=korps_unit.pk)
        create(
            c,
            org_base(cal["a"]),
            title="Korps intern",
            department_id=korps_unit.pk,
            visibility="board",
        )
        assert {"Korpsrat", "Korps intern"} <= set(titles(c, org_base(cal["a"])))

    def test_eingeladen_nur_mitglieder_der_untereinheit(self, cal, korps, board_a, api):
        _, zug = korps
        im_zug, user, access = member_with_access(cal["a"], "Erika", depts=[zug])
        _, other, other_access = member_with_access(cal["a"], "Hans")
        data = create(api(board_a), org_base(cal["a"]), title="Zugabend", department_id=zug.pk)
        ev = Event.objects.get(pk=data["id"])
        assert list(rsvp.invited(ev).values_list("pk", flat=True)) == [im_zug.pk]
        assert "Zugabend" in titles(api(user), f"/api/portal/{access.pk}/")
        assert "Zugabend" not in titles(api(other), f"/api/portal/{other_access.pk}/")

    def test_zurueck_zur_einheit(self, cal, korps, board_a, api):
        _, zug = korps
        c = api(board_a)
        data = create(c, org_base(cal["a"]), title="Fest", department_id=zug.pk)
        resp = c.patch(
            f"{org_base(cal['a'])}events/{data['id']}/",
            {"department_id": None},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        assert Event.objects.get(pk=data["id"]).department_id is None

    def test_ohne_angabe_bleibt_es_bei_der_einheit(self, cal, korps, board_a, api):
        data = create(api(board_a), org_base(cal["a"]), title="Vereinsfest")
        assert Event.objects.get(pk=data["id"]).department_id is None


class TestGrenzen:
    def _post(self, client, org, **data):
        payload = {
            "title": "X",
            "starts_at": "2026-06-13T14:00:00",
            "ends_at": "2026-06-13T18:00:00",
            **data,
        }
        return client.post(f"{org_base(org)}events/", payload, content_type=JSON)

    def test_selbstverwaltete_untereinheit_abgelehnt(self, cal, selbst, board_a, api):
        eigen, darunter = selbst
        for unit in (eigen, darunter):
            resp = self._post(api(board_a), cal["a"], department_id=unit.pk)
            assert resp.status_code == 400
            assert "department_id" in resp.json()
        assert not Event.objects.filter(title="X").exists()

    def test_fremde_untereinheit_abgelehnt(self, cal, board_a, api):
        fremd = Department.objects.create(organization=cal["b"], name="Fremdzug")
        resp = self._post(api(board_a), cal["a"], department_id=fremd.pk)
        assert resp.status_code == 400

    def test_inaktive_untereinheit_abgelehnt(self, cal, korps, board_a, api):
        _, zug = korps
        zug.is_active = False
        zug.save()
        resp = self._post(api(board_a), cal["a"], department_id=zug.pk)
        assert resp.status_code == 400

    def test_unsinnige_angabe(self, cal, korps, board_a, api):
        resp = self._post(api(board_a), cal["a"], department_id="abc")
        assert resp.status_code == 400

    def test_selbstverwaltete_termine_bleiben_beim_zug(self, cal, selbst, board_a, api):
        eigen, _ = selbst
        ev = Event.objects.create(
            organization=cal["a"],
            department=eigen,
            title="Eigener Abend",
            starts_at="2026-05-01T18:00:00+02:00",
            ends_at="2026-05-01T22:00:00+02:00",
        )
        resp = api(board_a).patch(
            f"{org_base(cal['a'])}events/{ev.pk}/", {"title": "x"}, content_type=JSON
        )
        assert resp.status_code == 403
