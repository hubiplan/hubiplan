"""KI-Schnittstelle W2/W3 (docs/mcp.md): Gestaltung, Menü und Aufbau im Entwurf, Bilder über
Hochladelink oder freigegebene Server, Entwürfe für Social-Media-Beiträge. Alles erfunden."""

from __future__ import annotations

import base64
import datetime
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as HttpClient
from django.utils import timezone
from PIL import Image

from core import safehttp
from core.tenancy import rls_bypass
from website import upload_views
from website.models import ImageUploadLink, SocialDraft, WebsiteImage

from .factories import give_role, make_user
from .test_mcp_verein import call, club, connect, editor, rpc, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def manager(club):  # noqa: F811
    user = make_user("ki-vorstand@example.org", first_name="Max", last_name="Muster")
    give_role(user, club, permissions=["website.manage", "mcp.connect"], name="Webseite")
    return user


def picture(fmt="PNG", size=(400, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "blue").save(buf, fmt)
    return buf.getvalue()


def data_of(text: str):
    """JSON-Teil einer Werkzeugantwort (nach der ersten Leerzeile)."""
    return json.loads(text.split("\n\n", 1)[1])


def add_image(site, user, **extra) -> WebsiteImage:  # noqa: F811
    from website import content

    upload = SimpleUploadedFile("baum.png", picture(), content_type="image/png")
    image = content.store_image(site, upload, extra.get("caption", ""), "", user)
    for key, value in extra.items():
        setattr(image, key, value)
    image.save()
    return image


# --- Werkzeuge und Bereiche ---


def test_neue_werkzeuge_je_bereich(club, site, editor):  # noqa: F811
    token = connect(editor, club, scope="webseite.lesen")["access_token"]
    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert {"webseite_gestaltung_ansehen", "webseite_menue_ansehen", "bilder_suchen"} <= names
    assert {"webseite_gestaltung_aendern", "bild_hochladen_vorbereiten"}.isdisjoint(names)
    token = connect(editor, club)["access_token"]
    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert {"webseite_menue_aendern", "startseite_aufbau_aendern", "bild_von_adresse"} <= names
    # Weiterhin kein Werkzeug zum Veröffentlichen
    assert not {n for n in names if "veroeffentlich" in n or "domain" in n}


# --- Gestaltung, Menü, Aufbau ---


def test_gestaltung_nur_im_entwurf_und_nur_mit_verwalten(club, site, editor, manager):  # noqa: F811
    token = connect(manager, club)["access_token"]
    text, failed = call(token, "webseite_gestaltung_ansehen")
    assert not failed, text
    info = data_of(text)
    other = next(d["schluessel"] for d in info["designs"] if d["schluessel"] != info["design"])
    live = site.design
    text, failed = call(token, "webseite_gestaltung_aendern", design=other)
    assert not failed, text
    site.refresh_from_db()
    assert site.draft["design"] == other and site.design == live
    # Unbekanntes Design: Fehler der Oberfläche, nichts gespeichert
    _text, failed = call(token, "webseite_gestaltung_aendern", design="gibt-es-nicht")
    assert failed
    # Redaktion (nur Inhalte) darf nicht gestalten
    token = connect(editor, club)["access_token"]
    _text, failed = call(token, "webseite_gestaltung_aendern", design=other)
    assert failed


def test_menue_im_entwurf_mit_ueberschrift_und_link(club, site, manager):  # noqa: F811
    token = connect(manager, club)["access_token"]
    text, failed = call(token, "webseite_menue_ansehen")
    assert not failed, text
    before = data_of(text)["menue"]
    assert before
    text, failed = call(
        token,
        "webseite_menue_aendern",
        neu=[
            {"art": "ueberschrift", "name": "Verein"},
            {"art": "link", "name": "Kreisverband", "adresse": "https://kreis.example.org"},
        ],
    )
    assert not failed, text
    heading, link = data_of(text)["neue_schluessel"]
    assert (heading, link) == ("heading:1", "link:1")
    first = before[0]["schluessel"]
    text, failed = call(
        token,
        "webseite_menue_aendern",
        reihenfolge=[{"schluessel": heading, "unterpunkte": [first, link]}],
    )
    assert not failed, text
    site.refresh_from_db()
    assert site.draft["block_names"][heading] == "Verein"
    assert site.draft["menu_links"][link] == "https://kreis.example.org"
    # Fehlende Hauptpunkte kommen an ihren Standardplatz; die neue Überschrift steht hinten
    [node] = [n for n in site.draft["menu"] if n["key"] == heading]
    assert [c["key"] for c in node["children"]] == [first, link]
    # Veröffentlicht bleibt das alte Menü
    assert "heading:1" not in (site.block_names or {})
    text, _failed = call(token, "webseite_menue_ansehen")
    assert "Verein" in {n["name"] for n in data_of(text)["menue"]}
    # Link ohne https: abgelehnt
    _text, failed = call(
        token, "webseite_menue_aendern", neu=[{"art": "link", "name": "X", "adresse": "ftp://x"}]
    )
    assert failed
    # Veröffentlichen übernimmt das Menü
    from .test_mcp_verein import with_mfa

    resp = with_mfa(manager).post(f"/api/orgs/{club.pk}/website/design/publish/")
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.block_names["heading:1"] == "Verein"
    assert heading in {n["key"] for n in site.menu}
    assert not site.draft


def test_aufbau_der_startseite_im_entwurf(club, site, manager):  # noqa: F811
    token = connect(manager, club)["access_token"]
    text, failed = call(token, "startseite_bausteine")
    assert not failed and "faq" in text
    text, failed = call(
        token,
        "startseite_aufbau_aendern",
        neu=[
            {
                "art": "faq",
                "inhalt": {
                    "title": "Fragen",
                    "items": [{"question": "Wann?", "answer": "Sonntags."}],
                },
                "nach": "",
            }
        ],
        aus=["c:t1"],
        aussehen={"c:t1": {"hintergrund": "light"}},
    )
    assert not failed, text
    [key] = data_of(text)["neue_schluessel"]
    site.refresh_from_db()
    sections = site.draft["home_sections"]
    assert sections[0]["key"] == key and sections[0]["kind"] == "faq"
    own = next(s for s in sections if s["key"] == "c:t1")
    assert own["on"] is False and own["bg"] == "light"
    # Veröffentlichter Aufbau unverändert
    assert [s["key"] for s in site.home_sections] == ["greeting", "c:t1"]
    # Feste Abschnitte lassen sich nicht entfernen
    _text, failed = call(token, "startseite_aufbau_aendern", entfernen=["greeting"])
    assert failed
    text, failed = call(token, "startseite_aufbau_aendern", entfernen=[key])
    assert not failed, text
    site.refresh_from_db()
    assert key not in {s["key"] for s in site.draft["home_sections"]}


# --- Bilder ---


def test_bilder_suchen_ansehen_beschreiben(club, site, editor):  # noqa: F811
    image = add_image(site, editor, caption="Kirschbaum im Frühling")
    add_image(site, editor, caption="Schützenfest")
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "bilder_suchen", suche="kirschbaum")
    assert not failed
    assert [r["nummer"] for r in data_of(text)] == [image.pk]
    resp = rpc(token, "tools/call", {"name": "bild_ansehen", "arguments": {"nummer": image.pk}})
    result = resp.json()["result"]
    assert not result["isError"], result
    shown, note = result["content"]
    assert shown["type"] == "image" and shown["mimeType"] == "image/jpeg"
    with Image.open(io.BytesIO(base64.b64decode(shown["data"]))) as img:
        assert max(img.size) <= 640
    assert note["type"] == "text" and "Personen" in note["text"]
    text, failed = call(token, "bild_beschreiben", nummer=image.pk, alternativtext="Blühender Baum")
    assert not failed, text
    image.refresh_from_db()
    assert image.alt_text == "Blühender Baum"


def test_benutzte_bilder_nur_ergaenzen(club, site, editor):  # noqa: F811
    image = add_image(site, editor, alt_text="Fahne")
    site.home_sections = [
        {"key": "greeting", "on": True},
        {"key": "c:b1", "kind": "banner", "on": True, "data": {"image": image.pk}},
    ]
    site.save()
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "bild_beschreiben", nummer=image.pk, alternativtext="Neu")
    assert failed and "HUBIplan" in text
    text, failed = call(token, "bild_beschreiben", nummer=image.pk, bildunterschrift="Am Markt")
    assert not failed, text
    image.refresh_from_db()
    assert image.alt_text == "Fahne" and image.caption == "Am Markt"


def test_hochladelink(club, site, editor):  # noqa: F811
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "bild_hochladen_vorbereiten")
    assert not failed, text
    url = next(w for w in text.split() if "/bilder-hochladen/" in w)
    secret = url.rsplit("/", 1)[1]
    link = ImageUploadLink.objects.get(website=site)
    assert link.via == "KI-Assistent (Testassistent)" and link.created_by == editor
    assert link.token_hash != secret
    public = f"/api/public/website-images/{secret}/"
    info = HttpClient().get(public)
    assert info.status_code == 200, info.content
    assert info.json()["remaining"] == link.max_files
    assert "organization" in info.json()
    up = SimpleUploadedFile("feld.jpg", picture("JPEG"), content_type="image/jpeg")
    resp = HttpClient().post(public, {"file": up})
    assert resp.status_code == 201, resp.content
    assert resp.json()["remaining"] == link.max_files - 1
    with rls_bypass():
        image = WebsiteImage.objects.get(pk=resp.json()["id"])
    assert image.website_id == site.pk and image.uploaded_by_id == editor.pk
    # Kein Bild: abgelehnt und nicht gezählt
    bad = SimpleUploadedFile("x.jpg", b"kein bild", content_type="image/jpeg")
    assert HttpClient().post(public, {"file": bad}).status_code == 400
    link.refresh_from_db()
    assert link.uploaded == 1
    # Voll oder abgelaufen: nicht mehr gültig
    link.max_files = 1
    link.save()
    up = SimpleUploadedFile("feld.jpg", picture("JPEG"), content_type="image/jpeg")
    assert HttpClient().post(public, {"file": up}).status_code == 404
    link.max_files = 20
    link.expires_at = timezone.now() - datetime.timedelta(minutes=1)
    link.save()
    assert HttpClient().get(public).status_code == 404
    assert HttpClient().get("/api/public/website-images/falsch/").status_code == 404


def test_hochladelink_endet_mit_konto(club, site, editor):  # noqa: F811
    link, secret = ImageUploadLink.create(site, editor, "")
    public = f"/api/public/website-images/{secret}/"
    assert HttpClient().get(public).status_code == 200
    editor.is_active = False
    editor.save()
    assert HttpClient().get(public).status_code == 404


def test_bild_von_adresse_nur_von_freigegebenen_servern(
    club,  # noqa: F811
    site,  # noqa: F811
    editor,  # noqa: F811
    manager,
    monkeypatch,
):
    calls = []

    def fake(method, url, **kw):
        calls.append(url)
        ctype = "text/html" if url.endswith(".html") else "image/png"
        return safehttp.Response(200, {"Content-Type": ctype}, picture())

    monkeypatch.setattr(upload_views.safehttp, "request", fake)
    token = connect(editor, club)["access_token"]
    url = "https://cloud.example.org/s/abc/foto.png"
    text, failed = call(token, "bild_von_adresse", adresse=url, quelle="Foto: Verein")
    assert failed and "cloud.example.org" in text and not calls
    # Freigeben in Webseite › Domain (Recht „Webseite verwalten“)
    from .test_mcp_verein import with_mfa

    c = with_mfa(manager)
    resp = c.put(
        f"/api/orgs/{club.pk}/website/",
        {"image_hosts": ["Cloud.Example.org", "127.0.0.1"]},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    resp = c.put(
        f"/api/orgs/{club.pk}/website/",
        {"image_hosts": ["Cloud.Example.org", "cloud.example.org"]},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.image_hosts == ["cloud.example.org"]
    text, failed = call(
        token, "bild_von_adresse", adresse=url, quelle="Foto: Verein", alternativtext="Wiese"
    )
    assert not failed, text
    image = WebsiteImage.objects.get(website=site)
    assert image.caption == "Quelle: Foto: Verein" and image.alt_text == "Wiese"
    _text, failed = call(
        token, "bild_von_adresse", adresse="https://cloud.example.org/x.html", quelle="Q"
    )
    assert failed
    _text, failed = call(
        token, "bild_von_adresse", adresse="http://cloud.example.org/a.png", quelle="Q"
    )
    assert failed


# --- Social Media ---


def test_social_entwurf(club, site, editor):  # noqa: F811
    club.enabled_modules = [*club.enabled_modules, "social"]
    club.save()
    image = add_image(site, editor)
    token = connect(editor, club)["access_token"]
    text, failed = call(
        token,
        "social_beitrag_entwerfen",
        text="Morgen ist Schützenfest! #musterstadt",
        bilder=[image.pk],
        kanal="instagram",
    )
    assert not failed, text
    draft = SocialDraft.objects.get(website=site)
    assert draft.images == [image.pk] and draft.via == "KI-Assistent (Testassistent)"
    _text, failed = call(token, "social_beitrag_entwerfen", text="X", bilder=[999999])
    assert failed
    text, failed = call(token, "social_entwuerfe")
    assert not failed and data_of(text)[0]["nummer"] == draft.pk
    # In HUBIplan: als erledigt markieren und löschen
    from .test_mcp_verein import with_mfa

    c = with_mfa(editor)
    base = f"/api/orgs/{club.pk}/website/social/drafts/"
    data = c.get(base).json()
    assert data["can_manage"] and data["drafts"][0]["images"][0]["id"] == image.pk
    resp = c.put(f"{base}{draft.pk}/", {"done": True}, content_type="application/json")
    assert resp.status_code == 200, resp.content
    draft.refresh_from_db()
    assert draft.done_at is not None
    assert c.delete(f"{base}{draft.pk}/").status_code == 204
    assert not SocialDraft.objects.exists()


def test_neue_tabellen_haben_rls():
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class WHERE relname IN "
            "('website_imageuploadlink', 'website_socialdraft') AND relrowsecurity"
        )
        assert {row[0] for row in cur.fetchall()} == {
            "website_imageuploadlink",
            "website_socialdraft",
        }
