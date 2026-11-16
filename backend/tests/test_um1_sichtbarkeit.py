"""Ergebnis einer Umfrage nach dem Start nur verschärfen; anonym erst nach dem Ende.

Gesamtaudit 15.11., UM-1: Das Feld „Befragte sehen das Ergebnis“ ließ sich nach dem Start von
„nur die Verwaltung“ auf „immer“ stellen; danach sah jedes Mitglied alle Freitexte, die unter
der Zusage „nur für die Verwaltung“ abgegeben waren. Fachfrage FF-22 (a): Anonyme Umfragen
zeigen ihr Ergebnis erst nach dem Ende, auch der Verwaltung. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import importlib

import pytest
from django.apps import apps as django_apps

from surveys.models import Survey

from .test_umfragen import JSON, answer, new_survey, ok, setup, start  # noqa: F401

pytestmark = pytest.mark.django_db
TEXT = {"kind": "text", "text": "Was stört dich?", "required": False}


def _patch(s, survey, **data):
    return s["chef"].patch(f"{s['url']}{survey['id']}/", data, content_type=JSON)


def test_ergebnis_nach_dem_start_nicht_lockern(setup):
    s = setup
    survey = new_survey(s, [TEXT], results="managers")
    start(s, survey)
    client, url = s["portals"]["Anna"]
    q = ok(client.get(url))["surveys"][0]["questions"][0]
    answer(s, "Anna", survey, [{"question": q["id"], "text": "Vertraulich an den Vorstand"}])
    # Vorher: 200, danach sah Bernd Annas Text
    for looser in ("always", "after_answer", "after_close"):
        assert _patch(s, survey, results=looser).status_code == 400
    assert Survey.objects.get(pk=survey["id"]).results == "managers"
    bernd, url_b = s["portals"]["Bernd"]
    row = ok(bernd.get(url_b))["surveys"][0]
    assert row["results"] is None


def test_verschaerfen_geht_nach_dem_start(setup):
    s = setup
    survey = new_survey(s, [TEXT], results="always")
    start(s, survey)
    assert _patch(s, survey, results="after_close").status_code == 200
    assert _patch(s, survey, results="managers").status_code == 200
    assert _patch(s, survey, results="always").status_code == 400


def test_anonym_nur_mit_ergebnis_nach_dem_ende(setup):
    s = setup
    url = s["url"]
    data = {"title": "Stimmung", "questions": [TEXT], "names": "anonymous"}
    for loose in ("always", "after_answer"):
        resp = s["chef"].post(url, {**data, "results": loose}, content_type=JSON)
        assert resp.status_code == 400, loose
    for strict in ("after_close", "managers"):
        assert (
            s["chef"].post(url, {**data, "results": strict}, content_type=JSON).status_code == 201
        )
    # Ohne Angabe oder beim Umstellen auf anonym: gleich „nach dem Ende“
    made = ok(s["chef"].post(url, data, content_type=JSON))
    assert made["results"] == "after_close"
    other = new_survey(s, [TEXT], results="always")
    assert ok(_patch(s, other, names="anonymous"))["results"] == "after_close"


def test_datenmigration_verschaerft_nur_laufende_anonyme(setup):
    s = setup
    org = s["org"]

    from core.tenancy import rls_bypass

    def make(**kw):
        with rls_bypass():
            return Survey.objects.create(organization=org, title="X", **kw)

    loose = make(names="anonymous", results="always", status="open")
    answered = make(names="anonymous", results="after_answer", status="draft")
    managers = make(names="anonymous", results="managers", status="open")
    closed = make(names="anonymous", results="always", status="closed")
    named = make(names="managers", results="always", status="open")
    migration = importlib.import_module("surveys.migrations.0003_anonym_ergebnis_nach_ende")

    class Editor:
        class connection:
            alias = "default"

    with rls_bypass():
        migration.tighten(django_apps, Editor)
    with rls_bypass():
        got = {x.pk: x.results for x in Survey.objects.filter(organization=org)}
    assert got[loose.pk] == "after_close" and got[answered.pk] == "after_close"
    assert got[managers.pk] == "managers"
    assert got[closed.pk] == "always" and got[named.pk] == "always"
