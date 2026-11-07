"""Gemeinsame Treffer, getrennte Ranglisten und Infrastruktur (erfundene Daten)."""

from decimal import Decimal

import pytest

from competitions.models import Competition, Hit, Score, Scoring

from .test_wettbewerbe import _starter, url


@pytest.fixture
def shooting_org(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "competitions", "shooting"]
    org.save()
    return org


def setup_competition(client, org):
    response = client.post(
        url(org),
        {
            "title": "Vereinsprobe",
            "date": "2027-05-01",
            "template": "schiessen",
        },
        "application/json",
    )
    assert response.status_code == 201, response.content
    comp_id = response.json()["id"]
    data = client.get(url(org, f"{comp_id}/")).json()
    program = data["programs"][0]
    response = client.patch(
        url(org, f"{comp_id}/programs/{program['id']}/"),
        {
            "target": "lg10_kyf",
            "shots": 5,
        },
        "application/json",
    )
    assert response.status_code == 200, response.content
    return comp_id, data["scorings"][0]["id"], program["id"]


def add_teiler(client, org, comp_id, program_id):
    response = client.post(
        url(org, f"{comp_id}/scorings/"),
        {
            "name": "Bester Teiler",
            "kind": "einzel",
            "program": program_id,
            "method": "teiler",
            "counted_shots": None,
        },
        "application/json",
    )
    assert response.status_code == 201, response.content
    return response.json()["id"]


def put_hits(client, org, comp_id, scoring_id, starter_id):
    response = client.put(
        url(org, f"{comp_id}/hits/"),
        {
            "scoring": scoring_id,
            "starter": starter_id,
            "hits": [{"x": x, "y": 0} for x in (0.5, 4, 8)],
        },
        "application/json",
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db(transaction=True)
class TestShootingPrograms:
    def test_einmal_treffer_mehrere_wertungen_und_loeschen(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        teiler = add_teiler(client, org, comp, program)
        starter = _starter(client, org, comp, name="Anna Probe")["id"]
        put_hits(client, org, comp, rings, starter)
        assert Score.objects.get(scoring_id=rings, starter_id=starter).value == 27
        assert Score.objects.get(scoring_id=teiler, starter_id=starter).value == Decimal("50.0")
        assert Hit.objects.filter(program_id=program).count() == 3
        data = client.post(url(org, f"{comp}/sync/"), {"ops": []}, "application/json").json()
        assert data["starters"][0]["hits"][str(rings)] == data["starters"][0]["hits"][str(teiler)]
        assert client.delete(url(org, f"{comp}/scorings/{rings}/")).status_code == 204
        assert Hit.objects.filter(program_id=program).count() == 3
        response = client.get(url(org, f"{comp}/hits/?scoring={teiler}&starter={starter}"))
        assert response.json()["total"] == "50.0"

    def test_neue_wertung_nutzt_bereits_erfasste_treffer(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        starter = _starter(client, org, comp, name="Anna Probe")["id"]
        put_hits(client, org, comp, rings, starter)
        teiler = add_teiler(client, org, comp, program)
        assert Score.objects.get(scoring_id=teiler, starter_id=starter).value == 50

    def test_aenderung_bestaetigen_neuberechnen_und_offline_sperren(
        self, shooting_org, board_a, api
    ):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        starter = _starter(client, org, comp, name="Anna Probe")["id"]
        put_hits(client, org, comp, rings, starter)
        generation = Competition.objects.get(pk=comp).generation
        endpoint = url(org, f"{comp}/programs/{program}/")
        response = client.patch(endpoint, {"target": "lp10"}, "application/json")
        assert response.status_code == 400 and "confirm_recalculation" in response.json()
        assert (
            client.patch(
                endpoint, {"target": "lp10", "confirm_recalculation": True}, "application/json"
            ).status_code
            == 200
        )
        assert Score.objects.get(scoring_id=rings, starter_id=starter).value == 30
        response = client.post(
            url(org, f"{comp}/sync/"),
            {
                "generation": generation,
                "ops": [{"op": "score", "starter": starter, "scoring": rings, "value": "1"}],
            },
            "application/json",
        )
        assert response.json()["results"][0]["ok"] is False
        assert Score.objects.get(scoring_id=rings, starter_id=starter).value == 30

    def test_manuelle_summe_bleibt_auch_mit_vorhandenen_treffern(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        starter = _starter(client, org, comp, name="Anna Probe")["id"]
        put_hits(client, org, comp, rings, starter)
        response = client.put(
            url(org, f"{comp}/scores/"),
            {"scoring": rings, "starter": starter, "value": "20"},
            "application/json",
        )
        assert response.status_code == 200
        assert not Score.objects.get(scoring_id=rings, starter_id=starter).from_hits
        assert (
            client.patch(
                url(org, f"{comp}/programs/{program}/"),
                {"target": "lp10", "confirm_recalculation": True},
                "application/json",
            ).status_code
            == 200
        )
        assert Score.objects.get(scoring_id=rings, starter_id=starter).value == 20

    def test_bedingungen_pruefen_und_fremde_grundlagen_abweisen(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        other, _, other_program = setup_competition(client, org)
        assert other != comp
        assert (
            client.patch(
                url(org, f"{comp}/scorings/{rings}/"),
                {"program": other_program},
                "application/json",
            ).status_code
            == 400
        )
        endpoint = url(org, f"{comp}/programs/{program}/")
        assert client.patch(endpoint, {"shots": 2}, "application/json").status_code == 400
        assert client.patch(endpoint, {"distance": 25}, "application/json").status_code == 400
        assert client.patch(endpoint, {"target": "eigen"}, "application/json").status_code == 400
        starter = _starter(client, org, comp, name="Anna Probe")["id"]
        put_hits(client, org, comp, rings, starter)
        response = client.post(
            url(org, f"{comp}/programs/"),
            {"name": "Zweiter Durchgang", "target": "lg10_kyf", "shots": 5},
            "application/json",
        )
        assert response.status_code == 201
        assert (
            client.patch(
                url(org, f"{comp}/scorings/{rings}/"),
                {"program": response.json()["id"], "confirm_recalculation": True},
                "application/json",
            ).status_code
            == 400
        )

    def test_kopie_erhaelt_gemeinsame_grundlage_ohne_ergebnisse(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        add_teiler(client, org, comp, program)
        put_hits(client, org, comp, rings, _starter(client, org, comp, name="Anna Probe")["id"])
        response = client.post(url(org, f"{comp}/copy/"), {}, "application/json")
        assert response.status_code == 201
        copied = client.get(url(org, f"{response.json()['id']}/")).json()
        assert len(copied["programs"]) == 1
        assert copied["programs"][0]["id"] != program
        assert {s["program"] for s in copied["scorings"] if s["kind"] == "einzel"} == {
            copied["programs"][0]["id"]
        }
        assert not copied["programs"][0]["has_results"]

    def test_fertiger_wettbewerb_und_rechte(self, shooting_org, board_a, board_b, api):
        client, org = api(board_a), shooting_org
        comp, rings, program = setup_competition(client, org)
        endpoint = url(org, f"{comp}/programs/{program}/")
        assert api(board_b).get(endpoint).status_code in (403, 404)
        Competition.objects.filter(pk=comp).update(status="endgueltig")
        assert client.patch(endpoint, {"name": "Anders"}, "application/json").status_code == 400
        assert client.delete(endpoint).status_code == 400
        assert client.delete(url(org, f"{comp}/scorings/{rings}/")).status_code == 400
        assert (
            client.post(
                url(org, f"{comp}/programs/"), {"name": "Neu"}, "application/json"
            ).status_code
            == 400
        )

    def test_alte_clients_erhalten_getrennte_durchgaenge(self, shooting_org, board_a, api):
        client, org = api(board_a), shooting_org
        comp, _, _ = setup_competition(client, org)
        data = {
            "name": "Eigenes Schießen",
            "kind": "einzel",
            "target": "lg10_kyf",
            "method": "ringe",
        }
        first = client.post(url(org, f"{comp}/scorings/"), data, "application/json").json()
        second = client.post(url(org, f"{comp}/scorings/"), data, "application/json").json()
        assert first["program"] != second["program"]
        assert Scoring.objects.get(pk=first["id"]).program.target == "lg10_kyf"


@pytest.mark.django_db(transaction=True)
def test_infrastruktur_filtert_kombinationen_und_belaesst_katalog(shooting_org, board_a, api):
    org, client = shooting_org, api(board_a)
    endpoint = f"/api/orgs/{org.pk}/"
    assert (
        client.patch(
            endpoint, {"shooting_facilities": ["unbekannt"]}, "application/json"
        ).status_code
        == 400
    )
    response = client.patch(
        endpoint, {"shooting_facilities": ["lg10", "p50", "lg10", "vogel"]}, "application/json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["shooting_facilities"] == ["lg10", "p50", "vogel"]
    catalog = client.get(url(org, "targets/")).json()
    assert catalog["infrastructure_configured"]
    assert "lg10_kyf5" in catalog["recommended_targets"] and "p25" in catalog["recommended_targets"]
    assert (
        "kk50" not in catalog["recommended_targets"]
        and "lp10" not in catalog["recommended_targets"]
    )
    assert "kk50" in {t["key"] for t in catalog["targets"]}
    assert (
        client.patch(endpoint, {"shooting_facilities": []}, "application/json").status_code == 200
    )
    assert client.get(url(org, "targets/")).json()["recommended_targets"] == []
    assert (
        client.patch(endpoint, {"shooting_facilities": None}, "application/json").status_code == 200
    )
    assert not client.get(url(org, "targets/")).json()["infrastructure_configured"]
