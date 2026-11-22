"""Menü frei anordnen (konzepte/menue-frei-anordnen.md): Speicherung, Prüfung, Rückgängig."""

import pytest
from rest_framework.exceptions import ValidationError

from organizations import menu_layout
from tests.factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"

STANDARD_IDS = [a["id"] for a in menu_layout.standard()["areas"]]


def _layout(*areas, **items):
    return {
        "v": 1,
        "areas": [a if isinstance(a, dict) else {"id": a} for a in areas],
        "items": items,
    }


def _url(org, rest=""):
    return f"/api/orgs/{org.pk}/menu-layout/{rest}"


def _summary(api, user, org):
    return next(o for o in api(user).get("/api/me/organizations/").json() if o["id"] == org.pk)


def test_standard_ohne_eigene_anordnung(api, orgs, board_a):
    club = orgs["a"]
    assert _summary(api, board_a, club)["menu_layout"] is None
    data = api(board_a).get(_url(club)).json()
    assert data["layout"] is None and data["owned"] is True and data["can_undo"] is False
    assert [a["id"] for a in data["standard"]["areas"]] == STANDARD_IDS


def test_menuepunkt_als_hauptmenuepunkt_und_verschieben(api, orgs, board_a):
    club = orgs["a"]
    layout = _layout(*STANDARD_IDS, "wettbewerbe", geschaeftspartner="verein")
    resp = api(board_a).put(_url(club), {"layout": layout}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    saved = resp.json()["layout"]
    assert saved["areas"][-1] == {"id": "wettbewerbe"}
    assert menu_layout.area_of(saved, "wettbewerbe") == "wettbewerbe"
    assert menu_layout.area_of(saved, "geschaeftspartner") == "verein"
    assert menu_layout.area_of(saved, "termine") == "planung"
    assert resp.json()["can_undo"] is True
    assert _summary(api, board_a, club)["menu_layout"] == saved


def test_eigener_bereich_mit_namen(api, orgs, board_a):
    club = orgs["a"]
    custom = {"id": "b1", "label": "  Schießsport ", "label_en": "Shooting", "icon": "wettbewerbe"}
    layout = _layout("start", "mitglieder", custom, "finanzen", wettbewerbe="b1")
    saved = api(board_a).put(_url(club), {"layout": layout}, content_type=JSON).json()["layout"]
    assert saved["areas"][2] == {
        "id": "b1",
        "label": "Schießsport",
        "label_en": "Shooting",
        "icon": "wettbewerbe",
    }
    # Menüpunkte entfallener Bereiche landen im ersten Bereich nach Start
    assert menu_layout.area_of(saved, "termine") == "mitglieder"
    assert menu_layout.area_of(saved, "finanzen") == "finanzen"


@pytest.mark.parametrize(
    "layout",
    [
        _layout("mitglieder", "start"),  # Start nicht vorn
        _layout("start"),  # zu wenige
        _layout("start", *[f"b{i}" for i in range(1, 13)]),  # zu viele (und ohne Namen)
        _layout("start", "start"),  # doppelt
        _layout("start", "unbekannt"),
        _layout("start", "plattform"),
        _layout("start", {"id": "b1"}),  # eigener Bereich ohne Namen
        _layout("start", {"id": "b1", "label": "x" * 25}),
        _layout("start", {"id": "b1", "label": "Neu", "icon": "<svg>"}),
        _layout("start", "verein", start="verein"),  # Startseite bleibt unter Start
        _layout("start", "verein", termine="planung"),  # Bereich fehlt
    ],
)
def test_ungueltige_anordnung(layout):
    with pytest.raises(ValidationError):
        menu_layout.clean(layout)


def test_unbekannte_menuepunkte_werden_uebergangen():
    cleaned = menu_layout.clean(_layout("start", "verein", gibtsnicht="verein", dsgvo="start"))
    assert cleaned["items"] == {"dsgvo": "start"}


def test_standard_wird_als_null_gespeichert():
    assert menu_layout.clean(_layout(*STANDARD_IDS)) is None


def test_rueckgaengig_und_standard(api, orgs, board_a):
    club = orgs["a"]
    first = _layout(*STANDARD_IDS, dsgvo="start")
    second = _layout(*STANDARD_IDS, dsgvo="finanzen")
    api(board_a).put(_url(club), {"layout": first}, content_type=JSON)
    api(board_a).put(_url(club), {"layout": second}, content_type=JSON)
    resp = api(board_a).post(_url(club, "undo/"), content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["layout"]["items"] == {"dsgvo": "start"}
    resp = api(board_a).put(_url(club), {"layout": None}, content_type=JSON)
    assert resp.json()["layout"] is None
    club.refresh_from_db()
    assert club.menu_layout is None
    assert len(club.menu_layout_history) == 3


def test_verlauf_haelt_fuenf(orgs, board_a):
    club = orgs["a"]
    for area in ["start", "planung", "finanzen", "verein", "mitglieder", "kommunikation", "start"]:
        menu_layout.save(club, _layout(*STANDARD_IDS, dsgvo=area), board_a)
    assert len(club.menu_layout_history) == menu_layout.HISTORY


def test_ohne_einstellungsrecht_nur_lesen(api, orgs):
    club = orgs["a"]
    reader = make_user("leser-a@example.org")
    give_role(reader, club, permissions=["members.view"], name="Leser")
    assert api(reader).get(_url(club)).status_code == 200
    resp = api(reader).put(_url(club), {"layout": None}, content_type=JSON)
    assert resp.status_code == 403
    assert api(reader).post(_url(club, "undo/"), content_type=JSON).status_code == 403


def test_fremder_verein_kein_zugriff(api, orgs, board_b):
    assert api(board_b).get(_url(orgs["a"])).status_code in (403, 404)


def test_untereinheit_uebernimmt_anordnung_des_vereins(orgs):
    from core.tenancy import rls_bypass
    from members.models import Department
    from organizations.models import Organization

    club = orgs["a"]
    club.menu_layout = menu_layout.clean(_layout(*STANDARD_IDS, dsgvo="start"))
    club.save(update_fields=["menu_layout"])
    with rls_bypass():
        zug = Department.objects.create(organization=club, name="Herolde", founding_year=1925)
        unit = Organization.objects.get(pk=zug.pk)
    assert menu_layout.effective(unit) == club.menu_layout
    assert menu_layout.owner(unit) == club


def test_gruppen_fuer_die_apps(orgs):
    club = orgs["a"]
    club.menu_layout = menu_layout.clean(
        _layout(
            "start",
            "mitglieder",
            {"id": "b1", "label": "Schießen", "label_en": "Shooting"},
            "finanzen",
            "verein",
            wettbewerbe="b1",
        )
    )
    groups = menu_layout.groups(club)
    assert [g["id"] for g in groups] == ["start", "mitglieder", "b1", "finanzen", "verein"]
    assert groups[2]["label"] == "Schießen" and "wettbewerbe" in groups[2]["items"]
    assert menu_layout.groups(club, lang="en")[2]["label"] == "Shooting"
    every = [i for g in groups for i in g["items"]]
    assert sorted(every) == sorted(menu_layout.item_ids())


def test_ki_hilfe_ersetzt_bereichsplatzhalter():
    from mcpserver.help_index import _clean

    assert _clean("unter {bereich:belegung}", {}) == "unter Planung"
    assert _clean("under {bereich:belegung}", {"__sprache__": "en"}) == "under Planning"
