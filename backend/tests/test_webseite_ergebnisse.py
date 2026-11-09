"""Wettbewerbe Schritt 5: Ergebnisse auf der Webseite (öffentliche Schnittstelle, alles
erfunden). Ralf 2026-11-01: eigener Baustein „Ergebnisse“ und Block auf der Startseite;
live fragt die Seite alle 15 Sekunden nach."""

import datetime
from decimal import Decimal

import pytest
from django.test import Client

from competitions.models import (
    AwardGrant,
    Competition,
    Placing,
    Score,
    Scoring,
    Series,
    Starter,
    Trophy,
)
from organizations.models import Department
from website import services
from website.models import Website

from .factories import make_member

pytestmark = pytest.mark.django_db(transaction=True)


def get(path):
    return Client().get(f"/api/public/site/v1/schluessel-a/{path}")


@pytest.fixture
def setup(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website", "competitions"]
    org.save()
    site = Website.objects.create(
        organization=org, public_key="schluessel-a", state="public", name_format="initial"
    )
    zug = Department.objects.create(organization=org, parent=org, name="Zug 1")
    max_ = make_member(org, "Max", "Muster", departments=[zug])
    erika = make_member(org, "Erika", "Beispiel", departments=[zug])
    jung = make_member(
        org, "Jonas", "Jung", departments=[zug], birth_date=datetime.date(2012, 5, 1)
    )
    reihe = Series.objects.create(organization=org, name="Vereinsmeisterschaft")
    comp = Competition.objects.create(
        organization=org,
        title="Vereinsmeisterschaft 2027",
        date=datetime.date(2027, 6, 14),
        website="abschluss",
        website_depth="alle",
        series=reihe,
    )
    einzel = Scoring.objects.create(organization=org, competition=comp, name="Einzel")
    zugw = Scoring.objects.create(
        organization=org,
        competition=comp,
        name="Zugwertung",
        kind="einheit",
        source=einzel,
        team_size=2,
    )
    st = {}
    for m, v in ((max_, 30), (erika, 28), (jung, 27)):
        s = Starter.objects.create(
            organization=org,
            competition=comp,
            membership=m,
            name=f"{m.person.first_name} {m.person.last_name}",
            unit=zug,
        )
        Score.objects.create(organization=org, scoring=einzel, starter=s, value=Decimal(v))
        st[m.person.first_name] = s
    gast = Starter.objects.create(
        organization=org, competition=comp, name="Gerd Gast", club="Nachbarverein"
    )
    Score.objects.create(organization=org, scoring=einzel, starter=gast, value=Decimal(20))
    return {
        "org": org,
        "site": site,
        "comp": comp,
        "max": max_,
        "erika": erika,
        "jung": jung,
        "reihe": reihe,
        "zugw": zugw,
        "st": st,
    }


class TestErgebnisse:
    def test_sichtbar_erst_nach_abschluss(self, setup):
        comp = setup["comp"]
        info = get("").json()
        assert info["results_url"].endswith("/results/")
        assert get("results/").json()["competitions"] == []
        comp.status = "laeuft"
        comp.save()
        assert get("results/").json()["competitions"] == []
        # live: schon während des Wettbewerbs, mit Vermerk und kurzer Zwischenspeicherung
        comp.website = "live"
        comp.save()
        data = get("results/").json()
        assert data["competitions"][0]["live"] is True and data["poll_seconds"] == 15
        url = data["competitions"][0]["id"]
        resp = get(f"results/{url}/")
        assert resp.status_code == 200 and "max-age=5" in resp["Cache-Control"]
        body = resp.json()
        assert body["poll_seconds"] == 15
        v1 = get(f"results/{url}/version/").json()["version"]
        score = Score.objects.get(starter=setup["st"]["Erika"])
        score.value = Decimal(29)
        score.save()
        assert get(f"results/{url}/version/").json()["version"] != v1
        # aus: nicht mehr da
        comp.website = "aus"
        comp.save()
        assert get(f"results/{url}/").status_code == 404

    def test_namen_einwilligung_und_umfang(self, setup):
        comp = setup["comp"]
        comp.status = "endgueltig"
        comp.save()
        token = get("results/").json()["competitions"][0]["id"]
        rows = get(f"results/{token}/").json()["scorings"][0]["rows"]
        names = [r["name"] for r in rows]
        # Namensform „Vorname N.“; unter 18 ohne Einwilligung ohne Namen; Gast mit Verein
        assert names == ["Max M.", "Erika B.", "ohne Namen", "Gerd G."]
        assert rows[3]["club"] == "Nachbarverein"
        services.set_entry(setup["jung"], "minor_res", True, "paper", None)
        services.set_entry(setup["max"], "results", True, "member", None)
        rows = get(f"results/{token}/").json()["scorings"][0]["rows"]
        assert [r["name"] for r in rows][:3] == ["ohne Namen", "Erika B.", "Jonas J."]
        assert rows[0]["place"] == 1  # der Platz bleibt
        comp.website_depth = "top3"
        comp.save()
        data = get(f"results/{token}/").json()
        assert len(data["scorings"][0]["rows"]) == 3 and not data["scorings"][0]["complete"]
        comp.website_depth = "einheiten"
        comp.save()
        data = get(f"results/{token}/").json()
        assert [s["name"] for s in data["scorings"]] == ["Zugwertung"]
        assert data["scorings"][0]["rows"][0]["name"] == "Zug 1"

    @pytest.mark.parametrize("own", [True, False])
    @pytest.mark.parametrize("prize_places", [0, 1, 2, 5, 10])
    def test_preisplaetze_je_wertung_und_startseite(self, setup, own, prize_places):
        org, comp = setup["org"], setup["comp"]
        comp.own = own
        comp.status = "endgueltig"
        comp.website_depth = "top3"  # Auch bisher gespeicherte Einstellungen gelten weiter.
        comp.save()
        first = comp.scorings.get(name="Einzel")
        first.prize_places = prize_places
        first.save()
        second = Scoring.objects.create(
            organization=org, competition=comp, name="Zweite Wertung", prize_places=2
        )
        for name, value in (("Anna Probe", 19), ("Otto Test", 18)):
            starter = Starter.objects.create(organization=org, competition=comp, name=name)
            Score.objects.create(organization=org, scoring=first, starter=starter, value=value)
        starters = list(comp.starters.order_by("pk"))
        for place, starter in enumerate(starters, 1):
            if not own:
                Placing.objects.create(
                    organization=org, scoring=first, starter=starter, place=place
                )
                Placing.objects.create(
                    organization=org, scoring=second, starter=starter, place=7 - place
                )
            else:
                Score.objects.create(organization=org, scoring=second, starter=starter, value=place)

        token = get("results/").json()["competitions"][0]["id"]
        detail = get(f"results/{token}/").json()
        home = get("results/?start=1").json()["competitions"][0]
        for data in (detail, home):
            name_key = "name" if data is detail else "scoring"
            scorings = {s[name_key]: s for s in data["scorings"]}
            rows = scorings["Einzel"]["rows"]
            assert [r["place"] for r in rows] == list(range(1, min(prize_places, 6) + 1))
            assert all(r["prize"] for r in rows)
            if prize_places >= 3:
                assert rows[2]["name"] == "ohne Namen"  # Minderjährig ohne Einwilligung.
            assert [r["place"] for r in scorings["Zweite Wertung"]["rows"]] == [1, 2]
            assert [r["name"] for r in scorings["Zweite Wertung"]["rows"]] == [
                "Otto T.",
                "Anna P.",
            ]
        assert detail["depth"] == "top3"
        assert detail["scorings"][0]["complete"] is False
        assert detail["scorings"][0]["field"] == 6
        if own:
            unit = next(s for s in detail["scorings"] if s["kind"] == "einheit")
            assert unit["complete"] is False
            assert unit["rows"][0]["name"] == "Zug 1"

    @pytest.mark.parametrize("depth", ["top3", "einheiten", "alle"])
    def test_zugwertung_nur_preisplaetze(self, setup, depth):
        """Ralf 2026-11-05: 3 Preisplätze in der Zugwertung, die Webseite zeigte 5 Züge."""
        org, comp, zugw = setup["org"], setup["comp"], setup["zugw"]
        comp.status = "endgueltig"
        comp.website_depth = depth
        comp.save()
        zugw.prize_places = 3
        zugw.save()
        einzel = comp.scorings.get(name="Einzel")
        for i, value in enumerate((26, 25, 24, 23), 2):
            zug = Department.objects.create(organization=org, parent=org, name=f"Zug {i}")
            for n in range(2):
                s = Starter.objects.create(
                    organization=org, competition=comp, name=f"Probe{i} Test{n}", unit=zug
                )
                Score.objects.create(
                    organization=org, scoring=einzel, starter=s, value=Decimal(value - n)
                )
        token = get("results/").json()["competitions"][0]["id"]
        scorings = get(f"results/{token}/").json()["scorings"]
        unit = next(s for s in scorings if s["kind"] == "einheit")
        names = [r["name"] for r in unit["rows"]]
        if depth == "alle":
            assert names == ["Zug 1", "Zug 2", "Zug 3", "Zug 4", "Zug 5"]
            assert unit["complete"] is True
        else:
            assert names == ["Zug 1", "Zug 2", "Zug 3"]
            assert all(r["prize"] for r in unit["rows"])
            assert unit["complete"] is False
        assert unit["field"] == 5

    def test_geteilte_preisplaetze_ohne_ungewertete_starter(self, setup):
        comp = setup["comp"]
        comp.status = "laeuft"
        comp.website = "live"
        comp.website_depth = "top3"
        comp.save()
        scoring = comp.scorings.get(name="Einzel")
        scoring.prize_places = 2
        scoring.save()
        score = Score.objects.get(scoring=scoring, starter=setup["st"]["Erika"])
        score.value = 27  # Erika und Jonas teilen sich den zweiten Preisplatz.
        score.save()
        gast = comp.starters.get(club="Nachbarverein")
        gast.out_of_competition = True
        gast.save()
        Starter.objects.create(organization=setup["org"], competition=comp, name="Ohne Wert")
        token = get("results/").json()["competitions"][0]["id"]
        for data in (
            get(f"results/{token}/").json(),
            get("results/?start=1").json()["competitions"][0],
        ):
            rows = data["scorings"][0]["rows"]
            assert [r["place"] for r in rows] == [1, 2, 2]
            assert [r["name"] for r in rows] == ["Max M.", "Erika B.", "ohne Namen"]

    def test_fremde_platzierungen_mit_luecken(self, setup):
        comp = setup["comp"]
        comp.own = False
        comp.status = "endgueltig"
        comp.website_depth = "top3"
        comp.save()
        scoring = comp.scorings.get(name="Einzel")
        scoring.prize_places = 5
        scoring.save()
        for starter, place in zip(comp.starters.order_by("pk"), [2, 4, 8, None], strict=True):
            Placing.objects.create(
                organization=setup["org"], scoring=scoring, starter=starter, place=place, value=20
            )
        token = get("results/").json()["competitions"][0]["id"]
        rows = get(f"results/{token}/").json()["scorings"][0]["rows"]
        assert [r["place"] for r in rows] == [2, 4]

    def test_einstellung_speichern_und_preisplaetze_live_aendern(self, setup, api, board_a):
        comp = setup["comp"]
        comp.status = "laeuft"
        comp.save()
        base = f"/api/orgs/{setup['org'].pk}/competitions/{comp.pk}/"
        client = api(board_a)
        response = client.patch(
            base, {"website": "live", "website_depth": "top3"}, "application/json"
        )
        assert response.status_code == 200
        comp.refresh_from_db()
        assert comp.website_depth == "top3"
        scoring = comp.scorings.get(name="Einzel")
        token = get("results/").json()["competitions"][0]["id"]
        for count in (1, 4, 0):
            before = get(f"results/{token}/version/").json()["version"]
            response = client.patch(
                f"{base}scorings/{scoring.pk}/", {"prize_places": count}, "application/json"
            )
            assert response.status_code == 200
            assert response.json()["prize_places"] == count
            scoring.refresh_from_db()
            assert scoring.prize_places == count
            assert get(f"results/{token}/version/").json()["version"] != before
            assert len(get(f"results/{token}/").json()["scorings"][0]["rows"]) == count

    def test_reihe_pokal_und_startseite(self, setup):
        org, comp = setup["org"], setup["comp"]
        comp.status = "endgueltig"
        comp.save()
        pokal = Trophy.objects.create(organization=org, name="Zugpokal")
        AwardGrant.objects.create(
            organization=org,
            competition=comp,
            series=setup["reihe"],
            year=2027,
            title="Vereinsmeister",
            name="Max Muster",
            membership=setup["max"],
        )
        AwardGrant.objects.create(
            organization=org,
            year=2026,
            trophy=pokal,
            name="Zug 1",
            unit_id=Department.objects.get(name="Zug 1").pk,
            manual=True,
        )
        AwardGrant.objects.create(
            organization=org,
            year=1999,
            series=setup["reihe"],
            title="Vereinsmeister",
            name="Karl Früher",
            manual=True,
        )
        data = get("results/").json()
        assert data["trophies"][0]["holders"] == [{"year": 2026, "name": "Zug 1", "kept": False}]
        serie = get(f"results/series/{data['series'][0]['id']}/").json()
        assert serie["years"][0]["winners"][0]["names"] == ["Max M."]
        assert {(t["year"], t["name"]) for t in serie["titles"]} == {
            (2027, "Max M."),
            (1999, "Karl F."),
        }
        start = get("results/?start=1").json()["competitions"]
        assert start[0]["title"] == "Vereinsmeisterschaft 2027"
        assert [r["name"] for r in start[0]["scorings"][0]["rows"]] == [
            "Max M.",
            "Erika B.",
            "ohne Namen",
        ]
        # Startseitenblock: erst an, wenn gewählt; nur mit Baustein und Modul
        site = setup["site"]
        assert "results" not in get("").json()["home"]
        site.home_sections = [{"key": "results", "on": True}]
        site.save()
        assert "results" in get("").json()["home"]
        site.blocks = {**site.blocks, "results": False}
        site.save()
        assert "results" not in get("").json()["home"]
        assert get("results/").status_code == 404

    def test_ohne_modul_nichts(self, setup):
        org = setup["org"]
        org.enabled_modules = ["members", "website"]
        org.save()
        assert get("results/").status_code == 404
        info = get("").json()
        assert info["results_url"] is None and "results" not in info["home"]
        assert all(n["key"] != "results" for n in info["nav"])


class TestMeineErgebnisse:
    def test_mitgliederbereich(self, setup, api):
        from portal.models import PortalAccess

        from .factories import make_user

        org, comp = setup["org"], setup["comp"]
        org.member_portal_enabled = True
        org.save()
        comp.status = "endgueltig"
        comp.save()
        AwardGrant.objects.create(
            organization=org,
            competition=comp,
            year=2027,
            title="Vereinsmeister",
            name="Max Muster",
            membership=setup["max"],
        )
        Competition.objects.create(
            organization=org, title="Noch in Vorbereitung", date=datetime.date(2028, 1, 1)
        )
        user = make_user("max@example.org")
        access = PortalAccess.objects.create(organization=org, membership=setup["max"], user=user)
        data = api(user).get(f"/api/portal/{access.pk}/results/").json()
        assert [s["title"] for s in data["starts"]] == ["Vereinsmeisterschaft 2027"]
        assert data["starts"][0]["results"][0]["place"] == 1
        assert [g["full_title"] for g in data["grants"]] == ["Vereinsmeister 2027"]
        info = api(user).get("/api/me/contexts/").json()["portal"][0]
        assert info["competitions_enabled"] is True
        # fremder Zugang: 404
        other = make_user("erika@example.org")
        assert api(other).get(f"/api/portal/{access.pk}/results/").status_code == 404


class TestZugseitenLinks:
    """Ralf 2026-11-09: Zugwertung und Zug in Klammern verlinken die Zugseite, falls die
    Webseite sie zeigt."""

    def _detail(self, setup):
        comp = setup["comp"]
        comp.status = "endgueltig"
        comp.save()
        token = get("results/").json()["competitions"][0]["id"]
        return get(f"results/{token}/").json()

    def test_kennung_der_zugseite(self, setup):
        data = self._detail(setup)
        slug = next(u["slug"] for u in get("units/").json()["units"] if u["name"] == "Zug 1")
        einzel, zug = data["scorings"]
        assert einzel["rows"][0]["unit_slug"] == slug
        assert "unit_slug" not in einzel["rows"][3]  # Gast ohne Zug
        assert zug["rows"][0]["unit_slug"] == slug

    def test_ohne_zugseite_keine_kennung(self, setup):
        site = setup["site"]
        site.units_mode = Website.Units.NONE
        site.save()
        data = self._detail(setup)
        assert all("unit_slug" not in r for s in data["scorings"] for r in s["rows"])
