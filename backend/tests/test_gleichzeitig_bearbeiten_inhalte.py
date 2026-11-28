# ruff: noqa: F811  (Fixtures als Parameter)
"""Gleichzeitiges Bearbeiten (core/versioning.py): Rundschreiben, Beiträge der Webseite und
Wertungen eines Wettbewerbs. Wer mit einer veralteten Fassung speichert, versendet,
veröffentlicht oder löscht, bekommt 409. Erfundene Daten."""

import pytest

from circulars.models import Circular
from competitions.models import Scoring
from website.models import NewsPost

from .factories import give_role, make_user, make_website
from .test_m12_events import JSON, board_fed, cal, private_root  # noqa: F401  (Fixtures)
from .test_rundschreiben import base, draft
from .test_schiessdurchgaenge import setup_competition, shooting_org  # noqa: F401
from .test_wettbewerbe import url as comp_url

pytestmark = pytest.mark.django_db


def _stale(resp, wort):
    assert resp.status_code == 409, resp.content
    detail = resp.json()["detail"]
    assert wort in detail and "inzwischen geändert. Bitte neu laden." in detail


def test_rundschreiben_veraltete_fassung(api, cal, board_a):
    c = api(board_a)
    root = base(cal["a"])
    entwurf = draft(c, root)
    one = f"{root}{entwurf['id']}/"
    alt = entwurf["version"]

    resp = c.patch(one, {"subject": "Einladung zum Fest", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > alt

    _stale(c.patch(one, {"subject": "Anders", "version": alt}, content_type=JSON), "Rundschreiben")
    # Versenden und Löschen nur in der Fassung, die die Person gesehen hat
    _stale(c.post(f"{one}send/", {"version": alt}, content_type=JSON), "Rundschreiben")
    _stale(c.delete(one, {"version": alt}, content_type=JSON), "Rundschreiben")
    circular = Circular.objects.get(pk=entwurf["id"])
    assert circular.subject == "Einladung zum Fest" and circular.is_draft

    # Ohne Fassung (ältere Oberfläche) wie bisher
    assert c.patch(one, {"subject": "Sommerfest"}, content_type=JSON).status_code == 200
    neu = c.get(one).json()["version"]
    assert c.delete(one, {"version": neu}, content_type=JSON).status_code == 204


def test_beitrag_der_webseite_veraltete_fassung(api, orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website"]
    org.save()
    make_website(org, public_key="fassung-a", state="public")
    redaktion = make_user("redaktion@example.org")
    give_role(redaktion, org, permissions=["website.content"], name="Redaktion")
    c = api(redaktion)
    root = f"/api/orgs/{org.pk}/website/news/"
    made = c.post(root, {"title": "Sommerfest", "date": "2019-06-15"}, content_type=JSON)
    assert made.status_code == 201, made.content
    post = made.json()
    one = f"{root}{post['id']}/"
    alt = post["version"]

    resp = c.put(one, {"body": "Ein schöner Tag.", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    neu = resp.json()["version"]
    assert neu > alt

    _stale(c.put(one, {"body": "Anders", "version": alt}, content_type=JSON), "Beitrag")
    _stale(c.post(f"{one}publish/", {"version": alt}, content_type=JSON), "Beitrag")
    _stale(c.delete(one, {"version": alt}, content_type=JSON), "Beitrag")
    stored = NewsPost.objects.get(pk=post["id"])
    assert stored.body == "Ein schöner Tag." and not stored.is_published

    resp = c.post(f"{one}publish/", {"version": neu}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_published"] is True


def test_wertung_veraltete_fassung(api, shooting_org, board_a):
    c, org = api(board_a), shooting_org
    comp, scoring_id, _program = setup_competition(c, org)
    data = c.get(comp_url(org, f"{comp}/")).json()
    scoring = next(s for s in data["scorings"] if s["id"] == scoring_id)
    one = comp_url(org, f"{comp}/scorings/{scoring_id}/")
    alt = scoring["version"]

    resp = c.patch(one, {"name": "Ringe", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] > alt

    _stale(c.patch(one, {"name": "Anders", "version": alt}, content_type=JSON), "Eintrag")
    _stale(c.delete(one, {"version": alt}, content_type=JSON), "Eintrag")
    assert Scoring.objects.get(pk=scoring_id).name == "Ringe"
