"""Inhalte der Startseiten-Abschnitte auch mit „Inhalte bearbeiten“ (Konzept webseite-baukasten
F7, Ralf 10.11.2026). Alle Daten erfunden."""

import pytest

from website.models import Website

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)

TEXT = {
    "key": "c:t1",
    "kind": "text",
    "on": True,
    "bg": "none",
    "width": "content",
    "column": "main",
    "data": {"title": "Über uns", "text": "Seit 1900."},
}


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    site = Website.objects.create(
        organization=club,
        public_key="inhalte-a",
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
    )
    site.home_sections = [{"key": "greeting", "on": True}, TEXT]
    site.save()
    return site


@pytest.fixture
def editor(club, api):
    user = make_user("abschnitt-inhalt@example.org")
    give_role(user, club, permissions=["website.content"], name="Schriftführer")
    return api(user)


@pytest.fixture
def manager(club, api):
    user = make_user("abschnitt-verwaltung@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club, path=""):
    return f"/api/orgs/{club.pk}/website/{path}"


def sections(c, club):
    return c.get(url(club)).json()["website"]["home_sections"]


def changed(current, **data):
    return [{**s, "data": {**s["data"], **data}} if s.get("kind") == "text" else s for s in current]


def test_inhalt_aendern_und_veroeffentlichen(club, site, editor):
    data = editor.get(url(club)).json()
    assert data["can_edit_home_content"] is True and data["can_manage"] is False
    resp = editor.put(
        url(club, "home-content/"),
        {"home_sections": changed(data["website"]["home_sections"], title="Unser Verein")},
        "application/json",
    )
    assert resp.status_code == 200, resp.content
    website = resp.json()["website"]
    assert website["draft"]["home_sections"][1]["data"]["title"] == "Unser Verein"
    assert website["draft_content_only"] is True
    site.refresh_from_db()
    assert site.home_sections[1]["data"]["title"] == "Über uns"
    resp = editor.post(url(club, "home-content/publish/"))
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.home_sections[1]["data"]["title"] == "Unser Verein" and site.draft == {}
    assert site.design_versions.count() == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda s: [s[1], s[0]],  # Reihenfolge
        lambda s: [s[0], {**s[1], "on": False}],  # ausschalten
        lambda s: [s[0], {**s[1], "bg": "light"}],  # Aussehen
        lambda s: [s[0]],  # löschen
        lambda s: [*s, {**TEXT, "key": "c:t2"}],  # hinzufügen
    ],
)
def test_aufbau_bleibt_der_verwaltung(club, site, editor, change):
    resp = editor.put(
        url(club, "home-content/"),
        {"home_sections": change(sections(editor, club))},
        "application/json",
    )
    assert resp.status_code == 400
    site.refresh_from_db()
    assert site.draft == {}


def test_entwurf_mit_gestaltung_veroeffentlicht_nur_die_verwaltung(club, site, editor, manager):
    manager.put(url(club), {"draft": {"style": {"font": "modern"}}}, "application/json")
    data = editor.get(url(club)).json()["website"]
    assert data["draft_content_only"] is False
    # Inhalt darf weiter in den Entwurf, veröffentlichen aber nicht
    resp = editor.put(
        url(club, "home-content/"),
        {
            "home_sections": changed(
                data["draft"].get("home_sections") or data["home_sections"], text="Neu."
            )
        },
        "application/json",
    )
    assert resp.status_code == 200, resp.content
    assert editor.post(url(club, "home-content/publish/")).status_code == 400
    # Die übrige Gestaltung bleibt der Verwaltung
    assert editor.put(url(club), {"draft": {"style": {}}}, "application/json").status_code == 403
    assert editor.post(url(club, "design/publish/")).status_code == 403
