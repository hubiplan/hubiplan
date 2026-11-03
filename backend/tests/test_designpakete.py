"""Designpakete: exportieren, prüfen, einspielen, freigeben (Ralf 2026-11-02, erfundene Daten)."""

import io
import json
import zipfile

import pytest
from django.test import Client

from organizations.models import Organization
from website import design_packages as dp
from website.models import DesignPackage, Website, WebsiteDomain

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
JSON = "application/json"

KOPF = """{% load seite i18n %}<header class="kopf"><a class="marke" href="{% url 'start' %}">
{% lokal site site.info.logo_url as logo %}{% if logo %}<img src="{{ logo }}" alt="">{% endif %}
<span>{{ site.info.name|default:"Webseite" }}</span></a></header>"""


def manifest(**over):
    data = {
        "format": dp.FORMAT,
        "version": 1,
        "key": "classic",
        "label": {"de": "Klassisch", "en": "Classic"},
        "hint": {"de": "Farbiger Kopf", "en": "Coloured header"},
        "roles": {"header": [0], "nav": [1], "footer": "dark"},
        "skizze_wie": "classic",
    }
    data.update(over)
    return data


def make_zip(files: dict | None = None, **over) -> bytes:
    files = {
        "design.json": json.dumps(manifest(**over)),
        "design.css": ".kopf { padding: 1rem; }\n",
        **(files or {}),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            if text is not None:
                z.writestr(name, text)
    return buf.getvalue()


def problems(data: bytes, **kw) -> list[str]:
    with pytest.raises(dp.PackageError) as exc:
        dp.read(data, **kw)
    return exc.value.problems


class TestPruefung:
    def test_skizze_frueherer_fassung(self):
        """Historische Layoutkennungen verwenden ein gepflegtes Standardlayout."""
        assert dp.read(make_zip(skizze_wie="classic-1"), key="hubertus").sketch_like == "classic"
        assert dp.read(make_zip(skizze_wie="gibtsnicht"), key="hubertus").sketch_like == "classic"

    def test_gutes_paket_unter_neuem_namen(self):
        pkg = dp.read(make_zip(), key="hubertus", label="Hubertus")
        assert pkg.key == "hubertus" and pkg.label == "Hubertus" and pkg.label_en == ""
        assert pkg.roles == {"header": [0], "nav": [1], "footer": "dark"}
        assert pkg.templates == {}
        assert len(pkg.content_hash) == 16

    def test_standardkuerzel_braucht_neuen_namen(self):
        assert any("Standarddesign" in p for p in problems(make_zip()))

    @pytest.mark.parametrize(
        "css",
        [
            "@import 'x.css';",
            "body { background: url(https://boese.example/x.png) }",
            "body { background: u\\72l(x) }",
            "@font-face { font-family: x }",
            "a { behavior: url(x.htc) }",
            "</style><script>alert(1)</script>",
        ],
    )
    def test_boeses_css_abgelehnt(self, css):
        assert problems(make_zip({"design.css": css}, key="test"))

    @pytest.mark.parametrize(
        "html",
        [
            "<script>alert(1)</script>",
            '<img src="x" onerror="alert(1)">',
            '<a href="javascript:alert(1)">x</a>',
            '<img src="https://boese.example/spur.png">',
            '<div style="background:url(x)">',
            "<iframe src=x></iframe>",
            "{{ site.info.name|safe }}",
            "{% autoescape off %}{{ x }}{% endautoescape %}",
            "{% load log %}",
            "{% load seite from i18n %}",
            '{% include "../../etc/passwd" %}',
            "{% include site.info.name %}",
            '{% extends "admin/base.html" %}',
            "{% debug %}",
            "{% filter safe %}x{% endfilter %}",
        ],
    )
    def test_boese_vorlage_abgelehnt(self, html):
        assert problems(make_zip({"vorlagen/kopf.html": html}, key="test"))

    def test_link_nach_aussen_erlaubt(self):
        html = '<a href="https://github.com/hubiplan" target="_blank" rel="noopener">HUBIplan</a>'
        assert problems(make_zip({"vorlagen/fuss.html": html}, key="test"))

    def test_kommentar_wird_nicht_geprueft(self):
        html = "{% comment %}<script>{% endcomment %}<p>ok</p>"
        assert problems(make_zip({"vorlagen/start.html": html}, key="test"))

    @pytest.mark.parametrize(
        "files",
        [
            {"design.css": None},
            {"design.json": None},
            {"skript.js": "alert(1)"},
            {"../design.css": "x"},
            {"vorlagen/termine.html": "<p>x</p>"},
            {"design.json": "kein json"},
            {"design.json": json.dumps(manifest(format="anderes", key="test"))},
            {"design.json": json.dumps(manifest(version=99, key="test"))},
            {"design.json": json.dumps(manifest(roles={"kopf": [9]}, key="test"))},
            {"design.json": json.dumps(manifest(key="Böse Name"))},
        ],
    )
    def test_kaputtes_paket_abgelehnt(self, files):
        assert problems(make_zip(files))

    def test_kein_zip(self):
        assert problems(b"nicht gezippt")

    def test_zu_gross_entpackt(self):
        big = "a" * (dp.MAX_UNPACKED_BYTES + 10)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("design.json", json.dumps(manifest(key="test")))
            z.writestr("design.css", big)
        assert any("5 MB" in p for p in problems(buf.getvalue()))

    def test_unbekannte_angaben_nur_hinweis(self):
        pkg = dp.read(make_zip(key="test", farbe_fuer_alles="#ff0000"))
        assert pkg.warnings and "farbe_fuer_alles" in pkg.warnings[0]

    def test_export_liest_sich_wieder(self):
        pkg = dp.read(make_zip(key="test"))
        data = dp.build_zip(
            key="test",
            label="Test",
            label_en="",
            hint="",
            hint_en="",
            roles=pkg.roles,
            sketch_like="classic",
            css=pkg.css,
            templates=pkg.templates,
            exported="2026-11-02",
        )
        again = dp.read(data)
        assert again.css == pkg.css and again.templates == pkg.templates
        assert again.content_hash == pkg.content_hash


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = [*org.enabled_modules, "website"]
    org.save()
    site = Website.objects.create(
        organization=org,
        public_key="schluessel-p",
        state="public",
        privacy_text="Datenschutz (erfunden)",
        privacy_published_text="Datenschutz (erfunden)",
    )
    WebsiteDomain.objects.create(organization=org, website=site, hostname="www.paket.example")
    return site


@pytest.fixture
def admin(orgs):
    # Plattformverwalter, der zugleich die Webseite des Vereins verwaltet
    user = make_user("plattform-paket@example.org")
    give_role(user, Organization.platform())
    give_role(user, orgs["a"])
    return user


def upload(c, org, data: bytes, **fields):
    f = io.BytesIO(data)
    f.name = "design-klassisch.zip"
    return c.post(f"/api/orgs/{org.pk}/website/design-packages/", {"file": f, **fields})


class TestEinspielen:
    def test_nur_plattformverwalter(self, api, orgs, board_a, site):
        resp = upload(api(board_a), orgs["a"], make_zip(key="hubertus"))
        assert resp.status_code == 403
        assert not DesignPackage.objects.exists()

    def test_pruefen_ohne_speichern(self, api, orgs, admin, site):
        resp = upload(
            api(admin), orgs["a"], make_zip(), key="hubertus", label="Hubertus", check="1"
        )
        assert resp.status_code == 200, resp.content
        assert resp.json()["package"]["key"] == "hubertus"
        assert not DesignPackage.objects.exists()

    def test_fehler_werden_genannt(self, api, orgs, admin, site):
        resp = upload(api(admin), orgs["a"], make_zip({"design.css": "@import 'x';"}, key="h2"))
        assert resp.status_code == 400
        assert "@import" in str(resp.json())

    def test_einspielen_waehlen_und_ausliefern(self, api, orgs, admin, board_a, site):
        c = api(admin)
        zipped = make_zip()
        resp = upload(c, orgs["a"], zipped, key="hubertus", label="Hubertus")
        assert resp.status_code == 201, resp.content
        pkg = DesignPackage.objects.get(key="hubertus")
        assert list(pkg.websites.all()) == [site]
        # Doppelt nur mit „ersetzen“
        assert upload(c, orgs["a"], zipped, key="hubertus", label="Hubertus").status_code == 400
        assert (
            upload(c, orgs["a"], zipped, key="hubertus", label="Hubertus", replace="1").status_code
            == 200
        )

        # Der Vorstand sieht und wählt das Design
        b = api(board_a)
        url = f"/api/orgs/{orgs['a'].pk}/website/"
        data = b.get(url).json()
        entry = next(d for d in data["designs"] if d["key"] == "hubertus")
        assert entry["package"] is True and entry["sketch"] == "classic"
        assert "hubertus" in data["website"]["design_colors"]
        assert data["can_import_designs"] is False
        resp = b.put(
            url,
            {"design": "hubertus", "color_roles": {"hubertus": {"footer": 1}}},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.content
        site.refresh_from_db()
        assert site.design == "hubertus" and site.color_roles == {"hubertus": {"footer": 1}}

        # Öffentliche Schnittstelle
        info = Client().get("/api/public/site/v1/schluessel-p/").json()
        assert info["design"] == "hubertus"
        assert info["design_packages"] == {
            "hubertus": {"label": "Hubertus", "hash": pkg.content_hash}
        }
        assert info["designs"]["hubertus"]["footer"]["color"] == info["theme"]["accent"]
        body = Client().get("/api/public/site/v1/schluessel-p/design/hubertus/").json()
        assert (
            body["css"].startswith(".kopf")
            and body["templates"] == {}
            and body["layout"] == "classic"
        )

        # Freigabe entziehen geht erst nach einem anderen Design; löschen ebenso
        detail = f"/api/orgs/{orgs['a'].pk}/website/design-packages/hubertus/"
        assert c.patch(detail, {"released": False}, content_type=JSON).status_code == 400
        assert c.delete(detail).status_code == 400
        b.put(url, {"design": "classic"}, content_type=JSON)
        assert c.patch(detail, {"released": False}, content_type=JSON).status_code == 200
        assert b.put(url, {"design": "hubertus"}, content_type=JSON).status_code == 400
        assert Client().get("/api/public/site/v1/schluessel-p/design/hubertus/").status_code == 404
        assert c.delete(detail).status_code == 204
        assert not DesignPackage.objects.exists()

    def test_fremde_webseite_sieht_paket_nicht(self, api, orgs, admin, site):
        upload(api(admin), orgs["a"], make_zip(), key="hubertus", label="Hubertus")
        other = Website.objects.create(organization=orgs["b"], public_key="schluessel-q")
        assert other.design_choices() == {"classic", "festive", "sidebar", "stage", "newspaper"}
        # Gespeichertes, aber nicht freigegebenes Design zählt als Klassisch
        other.design = "hubertus"
        other.save()
        assert other.effective_design() == "classic"

    def test_export_als_zip(self, api, orgs, admin, board_a, site):
        upload(
            api(admin),
            orgs["a"],
            make_zip(),
            key="hubertus",
            label="Hubertus",
        )
        resp = api(board_a).get(
            f"/api/orgs/{orgs['a'].pk}/website/design-packages/hubertus/export/"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"
        again = dp.read(resp.content)
        assert again.key == "hubertus" and not again.templates

    def test_farbzuordnung_aus_dem_standarddesign(self, api, orgs, admin, site):
        site.color_roles = {"classic": {"footer": 1, "header": "light"}}
        site.save()
        zipped = make_zip(quelle="classic")
        resp = upload(api(admin), orgs["a"], zipped, key="hubertus", label="Hubertus")
        assert resp.status_code == 201, resp.content
        site.refresh_from_db()
        assert site.color_roles["hubertus"] == {"footer": 1, "header": "light"}

    def test_steckbriefe_fuer_den_export(self, site):
        info = Client().get("/api/public/site/v1/schluessel-p/").json()
        classic = info["design_catalog"]["classic"]
        assert classic["label"] == "Klassisch" and classic["roles"]["header"] == [0]


@pytest.mark.parametrize(
    "html",
    [
        KOPF,
        "{% firstof '<script>alert(1)</script>' %}",
        "<scr{% if site.info.name %}ipt{% endif %}>x</script>",
        "{% if site.info.secret %}<img src=x onerror=alert(1)>{% endif %}",
        '{% cycle "<iframe src=https://evil.example>" "ok" %}',
        '<a href="java&#x73;cript:alert(1)">x</a>',
    ],
)
def test_fremde_vorlagen_unabhaengig_vom_kontext_abgelehnt(html):
    assert problems(make_zip({"vorlagen/kopf.html": html}, key="test"))


@pytest.mark.parametrize("layout", list(dp.designs.DESIGNS))
def test_standardlayout_export_import(layout):
    pkg = dp.read(make_zip(key="test", quelle=layout))
    assert pkg.sketch_like == layout and not pkg.templates
    assert pkg.content_hash != dp.content_hash(pkg.css, {}, pkg.roles, "unknown")


def test_altpaket_wird_oeffentlich_quarantaenisiert(site):
    pkg = DesignPackage.objects.create(
        key="altpaket", label="Alt", templates={"seite/kopf.html": KOPF}
    )
    pkg.websites.add(site)
    site.design = pkg.key
    site.save()
    response = Client().get("/api/public/site/v1/schluessel-p/")
    assert response.status_code == 200
    assert response.json()["design"] == "classic"
    assert pkg.key not in response.json()["design_packages"]
    assert Client().get("/api/public/site/v1/schluessel-p/design/altpaket/").status_code == 404
