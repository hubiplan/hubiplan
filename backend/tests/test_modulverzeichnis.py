"""Modulverzeichnis (access/modules.py): einzige Quelle der abschaltbaren Module."""

import pytest

from access import catalog
from access.modules import (
    GROUPS,
    MODULE_BY_ID,
    MODULES,
    with_requirements,
    without_dependents,
)


def test_katalog_liest_verzeichnis():
    assert set(catalog.SWITCHABLE_MODULES) == set(MODULE_BY_ID)
    assert set(catalog.DEFAULT_MODULES) == {m.id for m in MODULES if m.default}
    assert catalog.OPT_IN_MODULES == set(MODULE_BY_ID) - set(catalog.DEFAULT_MODULES)


def test_bereiche_gehoeren_zu_bekannten_modulen():
    for area in catalog.AREAS:
        for module in filter(None, area.module.split("|")):
            assert module in MODULE_BY_ID, (area.id, module)


def test_voraussetzungen_bekannt_und_gruppen_vorhanden():
    groups = {g.id for g in GROUPS}
    for m in MODULES:
        assert m.group in groups
        assert set(m.requires) | set(m.requires_any) <= set(MODULE_BY_ID), m.id


def test_voraussetzungen_einschalten_und_abhaengige_ausschalten():
    assert with_requirements(["music"]) == {"music", "events"}
    assert with_requirements(["meetings", "unbekannt"]) == {"meetings", "events"}
    assert without_dependents(["music", "meetings", "finance"]) == {"finance"}
    assert without_dependents(["music", "events"]) == {"music", "events"}


@pytest.mark.django_db
def test_api_liefert_gruppen(api):
    from .factories import make_user

    client = api(make_user("modul@example.org"))
    data = client.get("/api/modules/").json()
    ids = [m["id"] for g in data for m in g["modules"]]
    assert sorted(ids) == sorted(MODULE_BY_ID)
    music = next(m for g in data for m in g["modules"] if m["id"] == "music")
    assert music["requires"] == ["events"] and music["label"] == "Musik"
