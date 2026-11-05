"""Durchschnitt, Gewichtung, Vergleichbarkeit und Grenzen der Mitgliederstatistik."""

from decimal import Decimal

import pytest

from competitions.models import AwardGrant, Competition, Placing, Prize, Score, Scoring, Starter
from competitions.statistics import competition_statistics

from .factories import give_role, make_member, make_user
from .test_wettbewerbe import club  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def people(club):  # noqa: F811
    return [make_member(club, "Anna", "Weber"), make_member(club, "Bernd", "Müller")]


def add_competition(club, people, values, *, date="2026-06-01", status="endgueltig", **scoring):  # noqa: F811
    comp = Competition.objects.create(
        organization=club, title=f"Schießen {date}", date=date, status=status, discipline="LG 10 m"
    )
    options = dict(
        name="Einzelwertung",
        shots=5,
        counted_shots=3,
        method="ringe",
        unit_label="Ringe",
        max_per_shot=Decimal(10),
    )
    options.update(scoring)
    sc = Scoring.objects.create(organization=club, competition=comp, **options)
    starters = []
    for i, value in enumerate(values):
        m = people[i] if i < len(people) else None
        st = Starter.objects.create(
            organization=club,
            competition=comp,
            membership=m,
            name=f"{m.person.first_name} {m.person.last_name}" if m else "Gast",
        )
        if value is not None:
            Score.objects.create(organization=club, scoring=sc, starter=st, value=Decimal(value))
        starters.append(st)
    return comp, sc, starters


def test_averages_weighting_missing_results_and_guest_field(club, people):  # noqa: F811
    add_competition(club, people, [24, 18, 30], date="2025-06-01")
    add_competition(club, people, [30, 20], date="2026-06-01")
    add_competition(club, people, [27, None], date="2026-09-01")
    data = competition_statistics(club)
    assert data["summary"]["starts"] == 6
    assert data["summary"]["members"] == 2
    assert data["performance"]["count"] == 5
    assert data["performance"]["average"] == pytest.approx(23.8)
    assert data["performance"]["member_average"] == pytest.approx(23)
    assert data["performance"]["per_shot"] == pytest.approx(23.8 / 3)
    assert data["performance"]["best_names"] == ["Anna Weber"]
    assert data["performance"]["change"] == pytest.approx(77 / 3 - 21)
    result = next(
        r for r in data["results"] if r["date"] == "2025-06-01" and r["name"] == "Anna Weber"
    )
    assert (result["place"], result["field"]) == (2, 3)
    personal = competition_statistics(club, person_id=people[0].person_id, year=2026)
    assert personal["performance"]["average"] == pytest.approx(28.5)
    assert personal["performance"]["change"] == pytest.approx(4.5)
    assert personal["performance"]["per_shot"] == pytest.approx(9.5)
    assert {r["name"] for r in personal["results"]} == {"Anna Weber"}
    assert personal["years"] == [2026, 2025]


def test_real_zero_counts_but_provisional_and_out_of_competition_do_not(club, people):  # noqa: F811
    add_competition(club, people, [0, None])
    add_competition(club, people, [30, 30], status="laeuft")
    _, _, starters = add_competition(club, people, [30], date="2026-07-01")
    starters[0].out_of_competition = True
    starters[0].save()
    data = competition_statistics(club)
    assert data["summary"]["starts"] == 2
    assert data["performance"]["count"] == 1
    assert data["performance"]["average"] == 0
    assert data["performance"]["best"] == 0
    assert data["performance"]["change"] is None


def test_manually_entered_ring_totals_also_provide_ring_averages(club, people):  # noqa: F811
    add_competition(club, people, [27], method="frei", unit_label="Ringe")
    data = competition_statistics(club)
    assert data["selected_group"]["is_rings"] is True
    assert data["performance"]["average"] == 27
    assert data["performance"]["per_shot"] == 9


@pytest.mark.parametrize(
    "different",
    [
        {"counted_shots": 5},
        {"method": "zehntel", "decimals": 1},
        {"method": "teiler", "higher_better": False, "unit_label": "Teiler"},
        {"target": "lg10_dsb"},
    ],
)
def test_different_conditions_never_share_an_average(club, people, different):  # noqa: F811
    add_competition(club, people, [27])
    add_competition(club, people, [20], date="2026-07-01", **different)
    data = competition_statistics(club)
    assert data["performance"] is None
    assert len(data["group_summary"]) == 2
    group = next(g for g in data["group_summary"] if g["average"] == 27)
    filtered = competition_statistics(club, group_id=group["id"])
    assert filtered["performance"]["average"] == 27
    assert filtered["summary"]["starts"] == 1


def test_unknown_discipline_does_not_merge_competitions(club, people):  # noqa: F811
    for date in ("2025-06-01", "2026-06-01"):
        comp, _, _ = add_competition(club, people, [25], date=date)
        comp.discipline = ""
        comp.save()
    data = competition_statistics(club)
    assert data["performance"] is None
    assert len(data["groups"]) == 2


def test_multiple_scorings_count_one_start_and_teams_are_not_personal_wins(club, people):  # noqa: F811
    comp, sc, starters = add_competition(club, people, [28, 27])
    second = Scoring.objects.create(
        organization=club,
        competition=comp,
        name="Teiler",
        method="teiler",
        kind="einzel",
        higher_better=False,
        unit_label="Teiler",
    )
    for st, value in zip(starters, [100, 80], strict=True):
        Score.objects.create(organization=club, scoring=second, starter=st, value=value)
    Scoring.objects.create(
        organization=club, competition=comp, name="Zugwertung", kind="einheit", source=sc
    )
    data = competition_statistics(club)
    assert data["summary"]["starts"] == 2
    assert data["summary"]["wins"] == 2
    assert len(data["results"]) == 4
    teiler = next(g for g in data["group_summary"] if g["method"] == "teiler")
    assert teiler["best"] == 80
    assert teiler["per_shot"] is None


def test_bird_prizes_and_only_confirmed_awards(club, people):  # noqa: F811
    comp = Competition.objects.create(
        organization=club,
        title="Vogelschießen",
        date="2026-08-01",
        status="endgueltig",
        form="vogel",
    )
    st = Starter.objects.create(
        organization=club, competition=comp, membership=people[0], name="Anna Weber"
    )
    for name in ("Kopf", "Flügel"):
        Prize.objects.create(organization=club, competition=comp, name=name, winner=st)
    for state in ("", "bestaetigt", "vorschlag", "abgelehnt"):
        AwardGrant.objects.create(
            organization=club,
            competition=comp,
            membership=people[0],
            name="Anna Weber",
            year=2026,
            title="Titel",
            dignity_state=state,
        )
    data = competition_statistics(club, form="vogel")
    assert data["summary"]["starts"] == 1
    assert data["summary"]["prizes"] == 2
    assert data["summary"]["awards"] == 2
    assert data["summary"]["wins"] == 0
    assert data["performance"] is None
    assert data["results"][0]["prizes"] == ["Kopf", "Flügel"]


def test_foreign_places_keep_explicit_field_size(club, people):  # noqa: F811
    comp, sc, starters = add_competition(club, people, [None])
    comp.own = False
    comp.save()
    sc.field_size = 120
    sc.save()
    Placing.objects.create(organization=club, scoring=sc, starter=starters[0], value=29, place=3)
    data = competition_statistics(club)
    assert data["results"][0]["field"] == 120
    assert data["results"][0]["place"] == 3
    assert data["performance"]["average"] == 29


def test_change_uses_latest_comparable_year_not_later_bird_competition(club, people):  # noqa: F811
    add_competition(club, people, [24], date="2024-06-01")
    add_competition(club, people, [27], date="2025-06-01")
    comp = Competition.objects.create(
        organization=club,
        title="Vogelschießen",
        date="2026-08-01",
        status="endgueltig",
        form="vogel",
    )
    Starter.objects.create(
        organization=club, competition=comp, membership=people[0], name="Anna Weber"
    )
    data = competition_statistics(club, person_id=people[0].person_id)
    assert data["performance"]["previous_year"] == 2024
    assert data["performance"]["change"] == 3
    assert data["buckets"][-1]["average"] is None


def test_statistics_read_permissions_module_and_tenant(club, people, orgs, api):  # noqa: F811
    add_competition(club, people, [27, 26])
    reader = make_user("statistics-reader@example.org")
    give_role(reader, club, ["competitions.results"], name="Erfasser")
    c = api(reader)
    base = f"/api/orgs/{club.pk}/competitions/"
    response = c.get(base + "statistics/")
    assert response.status_code == 200, response.content
    assert response.json()["performance"]["average"] == 26.5
    other_member = make_member(orgs["b"], "Fremd", "Mitglied")
    assert c.get(base + f"statistics/?membership={other_member.pk}").status_code == 404
    assert c.get(base + "statistics/?year=0").status_code == 400
    assert c.get(base + "statistics/?form=ungültig").status_code == 400
    only_members = make_user("statistics-members@example.org")
    give_role(only_members, club, ["members.view"], name="Mitgliederleser")
    m = api(only_members)
    assert m.get(base + "statistics/").status_code == 403
    personal = m.get(base + f"member/{people[0].pk}/statistics/")
    assert personal.status_code == 200
    assert personal.json()["can_open"] is False
    assert {r["name"] for r in personal.json()["results"]} == {"Anna Weber"}
    club.enabled_modules = ["members"]
    club.save()
    assert c.get(base + "statistics/").status_code == 404


def test_portal_statistics_never_return_other_members(club, people, api):  # noqa: F811
    from portal.models import PortalAccess

    club.member_portal_enabled = True
    club.save(update_fields=["member_portal_enabled"])
    add_competition(club, people, [27, 30])
    user = make_user("statistics-anna@example.org")
    access = PortalAccess.objects.create(organization=club, membership=people[0], user=user)
    response = api(user).get(
        f"/api/portal/{access.pk}/competition-statistics/?membership={people[1].pk}"
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["performance"]["average"] == 27
    assert data["performance"]["best_names"] == ["Anna Weber"]
    assert data["members"] == []
    assert "member_options" not in data
    assert all("membership" not in r for r in data["results"])
    assert "Bernd" not in response.content.decode()
    outsider = make_user("statistics-outsider@example.org")
    assert api(outsider).get(f"/api/portal/{access.pk}/competition-statistics/").status_code == 404
