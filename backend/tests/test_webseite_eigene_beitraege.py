"""Eigene Beiträge unter „Aktuelles“ (Issue #707): Entwurf, Veröffentlichen, gemischte Liste
mit Instagram/Facebook, Archiv, Seite eines Beitrags, KI-Schnittstelle. Alles erfunden."""

# ruff: noqa: F811  (Fixtures als Parameter)

from __future__ import annotations

import datetime
import json

import pytest
from django.test import Client
from django.utils import timezone

from core.tenancy import rls_bypass
from organizations.models import Department
from website.models import NewsPost, SocialFeed, SocialPost

from .factories import give_role, make_user, make_website
from .test_mcp_verein import call, club, connect, editor  # noqa: F401
from .test_mcp_webseite_w2 import add_image, private_root  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

PUBLIC = "/api/public/site/v1/aktuell-a/"


@pytest.fixture
def setup(orgs):
    org = orgs["a"]
    # Ohne Modul „Social Media“: eigene Beiträge brauchen es nicht
    org.enabled_modules = ["members", "website"]
    org.save()
    site = make_website(org, public_key="aktuell-a", state="public")
    site.blocks = {**site.blocks, "search": True, "units": True}
    site.save()
    redaktion = make_user("redaktion@example.org")
    give_role(redaktion, org, permissions=["website.content"], name="Redaktion")
    return {"org": org, "site": site, "user": redaktion}


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/news/{rest}"


def new_post(c, org, **data):
    resp = c.post(
        url(org), {"title": "Sommerfest", "date": "2019-06-15", **data}, "application/json"
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def publish(c, org, pk):
    resp = c.post(url(org, f"{pk}/publish/"))
    assert resp.status_code == 200, resp.content
    return resp.json()


def public(path=""):
    return Client().get(PUBLIC + path)


def test_entwurf_erst_nach_veroeffentlichen_sichtbar(setup, api):
    org = setup["org"]
    c = api(setup["user"])
    post = new_post(c, org, body="Ein **schöner** Tag mit Musik.")
    assert post["slug"] == "sommerfest"
    assert post["is_published"] is False
    info = public().json()
    assert info["posts"]["own"] is False
    assert public(f"posts/eigene/{post['slug']}/").status_code == 404

    publish(c, org, post["id"])
    info = public().json()
    assert info["posts"]["own"] is True
    data = public("posts/").json()
    entry = data["posts"][0]
    assert entry["kind"] == "own" and entry["title"] == "Sommerfest"
    assert entry["date"] == "2019-06-15"
    assert entry["excerpt"] == "Ein schöner Tag mit Musik."
    assert entry["text"] == ""  # in der Liste nur der Anriss
    detail = public(f"posts/eigene/{post['slug']}/").json()["post"]
    assert detail["text"] == "Ein **schöner** Tag mit Musik."

    # Änderung im Entwurf bleibt verborgen, bis erneut veröffentlicht wird
    resp = c.put(url(org, f"{post['id']}/"), {"title": "Sommerfest 2019"}, "application/json")
    assert resp.status_code == 200 and resp.json()["has_changes"] is True
    assert public("posts/").json()["posts"][0]["title"] == "Sommerfest"
    publish(c, org, post["id"])
    assert public("posts/").json()["posts"][0]["title"] == "Sommerfest 2019"

    # Zurücknehmen
    resp = c.delete(url(org, f"{post['id']}/publish/"))
    assert resp.json()["is_published"] is False
    assert public().json()["posts"]["own"] is False


def test_gemischt_mit_social_media_nach_datum(setup, api):
    org, site = setup["org"], setup["site"]
    org.enabled_modules = [*org.enabled_modules, "social"]
    org.save()
    c = api(setup["user"])
    with rls_bypass():
        feed = SocialFeed.objects.create(
            organization=org, website=site, kind="instagram", status="ok", access_token="x"
        )
        for n, day in ((1, datetime.date(2020, 1, 10)), (2, datetime.date(2018, 3, 1))):
            SocialPost.objects.create(
                organization=org,
                feed=feed,
                external_id=str(n),
                media_type="text",
                text=f"Instagram {n}",
                published_at=timezone.make_aware(datetime.datetime.combine(day, datetime.time(9))),
            )
    publish(c, org, new_post(c, org, title="Konzert", date="2019-05-01")["id"])
    data = public("posts/").json()
    assert [p.get("title") or p["text"] for p in data["posts"]] == [
        "Instagram 1",
        "Konzert",
        "Instagram 2",
    ]
    assert data["more"] is False
    own = public("posts/?art=own").json()["posts"]
    assert [p["title"] for p in own] == ["Konzert"]
    insta = public("posts/?art=instagram").json()["posts"]
    assert [p["text"] for p in insta] == ["Instagram 1", "Instagram 2"]


def test_archiv_seitenweise(setup, api):
    org = setup["org"]
    c = api(setup["user"])
    for year in (2012, 2014, 2016, 2018, 2019):
        publish(c, org, new_post(c, org, title=f"Beitrag {year}", date=f"{year}-04-01")["id"])
    first = public("posts/?anzahl=2").json()
    assert [p["title"] for p in first["posts"]] == ["Beitrag 2019", "Beitrag 2018"]
    assert first["more"] is True and first["page"] == 1
    third = public("posts/?anzahl=2&seite=3").json()
    assert [p["title"] for p in third["posts"]] == ["Beitrag 2012"]
    assert third["more"] is False
    assert public("posts/?anzahl=2&seite=9").json()["posts"] == []


def test_bilder_und_videos(setup, api):
    org, site, user = setup["org"], setup["site"], setup["user"]
    c = api(user)
    with rls_bypass():
        foto = add_image(site, user, caption="Festzelt")
        vorschau = add_image(site, user, caption="Vorschau")
        im_text = add_image(site, user, caption="Plakat")
        fremd = add_image(site, user, caption="Nicht benutzt")
    post = new_post(
        c,
        org,
        body=f"Plakat: ![Plakat](bild:{im_text.key})",
        images=[foto.pk],
        videos=[
            {
                "url": "https://www.youtube.com/watch?v=abc",
                "title": "Ständchen",
                "image": vorschau.pk,
            }
        ],
    )
    publish(c, org, post["id"])
    entry = public("posts/").json()["posts"][0]
    assert [i["key"] for i in entry["images"]] == [foto.key]
    assert entry["videos"][0]["url"] == "https://www.youtube.com/watch?v=abc"
    assert entry["videos"][0]["image"]["key"] == vorschau.key
    for image in (foto, vorschau, im_text):
        assert public(f"images/{image.key}/").status_code == 200, image.caption
    assert public(f"images/{fremd.key}/").status_code == 404


@pytest.mark.parametrize(
    "data,field",
    [
        ({"videos": [{"url": "http://example.org/video"}]}, "videos"),
        ({"videos": [{"url": "javascript:alert(1)"}]}, "videos"),
        ({"images": [999999]}, "images"),
        ({"date": "gestern"}, "date"),
        ({"title": "  "}, "title"),
        ({"slug": "Mit Leerzeichen"}, "slug"),
    ],
)
def test_pruefungen(setup, api, data, field):
    org = setup["org"]
    c = api(setup["user"])
    post = new_post(c, org)
    resp = c.put(url(org, f"{post['id']}/"), data, "application/json")
    assert resp.status_code == 400, resp.content
    assert field in resp.json()


def test_adresse_eindeutig(setup, api):
    org = setup["org"]
    c = api(setup["user"])
    first = new_post(c, org)
    second = new_post(c, org)
    assert (first["slug"], second["slug"]) == ("sommerfest", "sommerfest-2")
    resp = c.put(url(org, f"{second['id']}/"), {"slug": "sommerfest"}, "application/json")
    assert resp.status_code == 400 and "slug" in resp.json()


def test_ohne_recht_nur_lesen(setup, api):
    org = setup["org"]
    viewer = make_user("lesen@example.org")
    give_role(viewer, org, permissions=["website.view"], name="Lesen")
    c = api(viewer)
    assert c.get(url(org)).status_code == 200
    resp = c.post(url(org), {"title": "X", "date": "2020-01-01"}, "application/json")
    assert resp.status_code == 404


def test_beitrag_einer_untereinheit(setup, api):
    org = setup["org"]
    with rls_bypass():
        unit = Department.objects.create(organization=org, parent=org, name="Jägerzug")
    c = api(setup["user"])
    publish(c, org, new_post(c, org, title="Zugabend", department=unit.pk)["id"])
    assert public("posts/").json()["posts"] == []
    zug = public("posts/?einheit=jaegerzug").json()["posts"]
    assert [p["title"] for p in zug] == ["Zugabend"]
    assert public("units/jaegerzug/").json()["posts"]["own"] is True


def test_baustein_aus(setup, api):
    org, site = setup["org"], setup["site"]
    c = api(setup["user"])
    publish(c, org, new_post(c, org)["id"])
    site.blocks = {**site.blocks, "posts": False}
    site.save()
    assert public("posts/").status_code == 404
    assert public("posts/eigene/sommerfest/").status_code == 404


# --- KI-Schnittstelle ---


@pytest.fixture
def ki_site(club):
    return make_website(club, public_key="aktuell-ki", state="public")


def test_ki_legt_nur_entwuerfe_an(club, ki_site, editor):
    token = connect(editor, club)["access_token"]
    text, failed = call(
        token,
        "beitrag_speichern",
        titel="Jubiläumskonzert",
        datum="2015-10-03",
        text="Rückblick auf das Konzert.",
        videos=[{"adresse": "https://www.youtube.com/watch?v=xyz", "titel": "Mitschnitt"}],
    )
    assert not failed, text
    with rls_bypass():
        post = NewsPost.objects.get(website=ki_site)
    assert post.title == "Jubiläumskonzert" and post.published_at is None
    assert post.date == datetime.date(2015, 10, 3)
    assert post.videos[0]["url"] == "https://www.youtube.com/watch?v=xyz"

    text, failed = call(token, "beitraege_ansehen")
    assert not failed and "Jubiläumskonzert" in text
    text, failed = call(token, "beitraege_ansehen", nummer=post.pk)
    assert not failed and json.loads(text)["text"] == "Rückblick auf das Konzert."

    text, failed = call(token, "beitrag_speichern", nummer=post.pk, titel="Jubiläum 2015")
    assert not failed, text
    with rls_bypass():
        post.refresh_from_db()
        assert post.title == "Jubiläum 2015" and post.published_at is None
        post.publish()
    # Veröffentlichte Beiträge löscht nur ein Mensch
    text, failed = call(token, "beitrag_loeschen", nummer=post.pk)
    assert failed
    with rls_bypass():
        assert NewsPost.objects.filter(pk=post.pk).exists()


def test_ki_nur_lesen_ohne_entwurfsbereich(club, ki_site, editor):
    token = connect(editor, club, scope="webseite.lesen")["access_token"]
    from .test_mcp_verein import rpc

    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert "beitraege_ansehen" in names
    assert {"beitrag_speichern", "beitrag_loeschen"}.isdisjoint(names)


def test_suche_findet_veroeffentlichte_beitraege(setup, api):
    org = setup["org"]
    c = api(setup["user"])
    draft = new_post(c, org, title="Probenwochenende", body="Wir proben im Musterwald.")
    hits = public("search/?q=Musterwald").json()["results"]
    assert not [h for h in hits if h.get("kind") == "news"]
    publish(c, org, draft["id"])
    hits = public("search/?q=Musterwald").json()["results"]
    assert [h["slug"] for h in hits if h.get("kind") == "news"] == ["probenwochenende"]
