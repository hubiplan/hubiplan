"""Einheiten Schritt 5: Einheiten umhängen."""

import pytest

from organizations.models import Department, Organization
from organizations.tree import MAX_DEPTH

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.department_label, club.department_label_plural = "Zug", "Züge"
    club.department_label_gender = "m"
    club.save()
    return club


def unit(club, name, parent=None):
    return Department.objects.create(
        organization=club, parent=parent or club, name=name, founding_year=1990
    )


def move(c, club, u, parent):
    return c.patch(
        f"/api/orgs/{club.pk}/departments/{u.pk}/", {"parent_unit": parent}, content_type=JSON
    )


class TestUntereinheitenUmhaengen:
    def test_gruppe_in_anderen_zug(self, api, club, board_a):
        a, b = unit(club, "Jägerzug"), unit(club, "Schützenzug")
        gruppe = unit(club, "Gruppe 1", a)
        resp = move(api(board_a), club, gruppe, b.pk)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["path"] == "Schützenzug › Gruppe 1"
        gruppe.refresh_from_db()
        assert gruppe.parent_id == b.pk

    def test_zug_unter_zug_bekommt_neue_bezeichnung(self, api, club, board_a):
        a, b = unit(club, "Jägerzug"), unit(club, "Schützenzug")
        assert b.label == "Zug"
        c = api(board_a)
        assert move(c, club, b, a.pk).status_code == 200
        b.refresh_from_db()
        assert b.label == "Gruppe"
        # und zurück nach oben
        assert move(c, club, b, None).status_code == 200
        b.refresh_from_db()
        assert (b.parent_id, b.label) == (club.pk, "Zug")

    def test_untereinheiten_und_mitglieder_wandern_mit(self, api, club, board_a):
        a, b = unit(club, "Jägerzug"), unit(club, "Schützenzug")
        gruppe = unit(club, "Gruppe 1", a)
        make_member(club, "Gerd", "Gruppe", departments=[gruppe])
        c = api(board_a)
        assert move(c, club, a, b.pk).status_code == 200
        rows = c.get(f"/api/orgs/{club.pk}/members/?abteilung={b.pk}").json()["results"]
        assert [r["first_name"] for r in rows] == ["Gerd"]
        paths = [r["path"] for r in c.get(f"/api/orgs/{club.pk}/departments/").json()]
        assert paths == [
            "Schützenzug",
            "Schützenzug › Jägerzug",
            "Schützenzug › Jägerzug › Gruppe 1",
        ]

    def test_tiefe_zaehlt_die_mitwandernden_ebenen(self, api, club, board_a):
        chain = [unit(club, "Ebene 1")]
        for level in range(2, MAX_DEPTH + 1):
            chain.append(unit(club, f"Ebene {level}", chain[-1]))
        other = unit(club, "Anderer Zug")
        sub = unit(club, "Darunter", other)
        # „Anderer Zug“ (2 Ebenen) unter Ebene 5 wären 7 Ebenen
        resp = move(api(board_a), club, other, chain[MAX_DEPTH - 2].pk)
        assert resp.status_code == 400
        assert "Ebenen" in str(resp.json())
        sub.refresh_from_db()
        assert sub.parent_id == other.pk

    def test_kein_kreis(self, api, club, board_a):
        a = unit(club, "Jägerzug")
        gruppe = unit(club, "Gruppe 1", a)
        assert move(api(board_a), club, a, gruppe.pk).status_code == 400


class TestVereinUmhaengen:
    @pytest.fixture
    def platform_admin(self):
        user = make_user("plattform@example.org")
        give_role(user, Organization.platform())
        return user

    def test_ohne_mitglieder_moeglich(self, api, orgs, platform_admin):
        club = orgs["c"]
        resp = api(platform_admin).patch(
            f"/api/platform/orgs/{club.pk}/",
            {"federation": orgs["federation"].pk},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        club.refresh_from_db()
        assert club.parent_id == orgs["federation"].pk

    def test_mit_mitgliedern_gesperrt(self, api, orgs, platform_admin):
        club = orgs["c"]
        make_member(club, "Erika", "Muster")
        resp = api(platform_admin).patch(
            f"/api/platform/orgs/{club.pk}/",
            {"federation": orgs["federation"].pk},
            content_type=JSON,
        )
        assert resp.status_code == 400
        assert "Datenübernahme" in str(resp.json())
        club.refresh_from_db()
        assert club.parent_id != orgs["federation"].pk


class TestGleichzeitigUmhaengen:
    """Gesamtaudit 10.11. V02: gegenläufiges Umhängen darf keinen Kreis erzeugen."""

    def test_zweite_anfrage_prueft_unter_sperre_neu(self, api, club, board_a, monkeypatch):
        from organizations.serializers import DepartmentSerializer

        a, b = unit(club, "Jägerzug"), unit(club, "Schützenzug")
        original = DepartmentSerializer.validate

        def validate_then_race(self, attrs):
            result = original(self, attrs)
            # Die andere Anfrage hängt B unter A, nachdem diese hier geprüft hat
            Department.objects.filter(pk=b.pk).update(parent_id=a.pk)
            return result

        monkeypatch.setattr(DepartmentSerializer, "validate", validate_then_race)
        resp = move(api(board_a), club, a, b.pk)
        assert resp.status_code == 400
        assert "parent_unit" in resp.json()
        a.refresh_from_db()
        assert a.parent_id == club.pk

    def test_vorhandener_kreis_endet_ohne_endlosschleife(self, club):
        a, b = unit(club, "Jägerzug"), unit(club, "Schützenzug")
        Department.objects.filter(pk=a.pk).update(parent_id=b.pk)
        Department.objects.filter(pk=b.pk).update(parent_id=a.pk)
        probe = Department(organization_id=club.pk, parent_id=a.pk)
        assert probe.parent_error()
