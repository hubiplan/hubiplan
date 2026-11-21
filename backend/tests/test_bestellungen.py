# ruff: noqa: F811  (Fixtures aus test_m9_billing)
"""Sammelbestellungen (Lückenliste 20.11.2026, B4): Artikel mit Größen, Frist, Höchstmengen,
Bestellen im Mitgliederbereich und in der App, Summen, freiwillige Rechnung, Ausgabe."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.models import Invoice
from core.tenancy import tenant_context
from members.models import MembershipPeriod
from orders.models import MemberOrder, OrderCampaign

from .factories import give_role, make_member, make_user
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def day(n):
    return (timezone.localdate() + datetime.timedelta(days=n)).isoformat()


@pytest.fixture
def shop(club, c, setup, zug, api):
    from portal.models import PortalAccess

    club.enabled_modules = sorted({*club.enabled_modules, "orders", "portal"})
    club.save()
    org = f"/api/orgs/{club.pk}"
    people, portals = {}, {}
    for first, depts in (("Anna", [zug]), ("Bernd", []), ("Carla", [])):
        m = make_member(club, first, "Muster", f"{first.lower()}@example.org", departments=depts)
        user = make_user(f"{first.lower()}-konto@example.org")
        access = PortalAccess.objects.create(organization=club, membership=m, user=user)
        people[first] = m
        portals[first] = (api(user), f"/api/portal/{access.pk}/orders/", access)
    return {"org": org, "url": f"{org}/orders/", "people": people, "portals": portals}


def new_campaign(c, shop, **extra):
    data = {
        "title": "Vereinskleidung 2027",
        "text": "Poloshirts und Kappen mit Vereinslogo.",
        "deadline": day(14),
        "articles": [
            {
                "name": "Poloshirt",
                "price": "25.00",
                "variants": ["S", "M", "L", "XL"],
                "variant_label": "Größe",
                "max_per_member": 3,
            },
            {"name": "Festschrift", "price": "10", "max_total": 3},
        ],
    }
    data.update(extra)
    camp = ok(c.post(shop["url"], data, content_type=JSON))
    return camp


def publish(c, shop, camp, action="publish"):
    return ok(c.post(f"{shop['url']}{camp['id']}/publish/", {"action": action}, content_type=JSON))


def order(client, url, camp, lines, code=200, **extra):
    resp = client.put(f"{url}{camp['id']}/order/", {"lines": lines, **extra}, content_type=JSON)
    assert resp.status_code == code, resp.content
    return resp.json()


def test_anlegen_freigeben_bestellen_aendern_summen(c, shop):
    camp = new_campaign(c, shop)
    assert camp["state"] == "draft" and len(camp["articles"]) == 2
    polo, heft = camp["articles"]
    client, url, _access = shop["portals"]["Anna"]
    # Entwurf: Mitglieder sehen nichts
    assert ok(client.get(url))["campaigns"] == []
    publish(c, shop, camp)
    data = ok(client.get(url))
    assert [r["id"] for r in data["campaigns"]] == [camp["id"]]
    assert data["campaigns"][0]["ordered"] is False
    detail = ok(client.get(f"{url}{camp['id']}/"))
    assert detail["can_order"] is True and detail["articles"][0]["price"] == "25.00"
    got = order(
        client,
        url,
        camp,
        [
            {"article": polo["id"], "variant": "M", "quantity": 2},
            {"article": heft["id"], "quantity": 1},
        ],
        note="Bitte mit Namen bestickt",
    )
    assert got["order"]["total"] == "60.00"
    assert got["order"]["note"] == "Bitte mit Namen bestickt"
    # Ändern bis zur Frist ersetzt die ganze Bestellung
    got = order(client, url, camp, [{"article": polo["id"], "variant": "L", "quantity": 1}])
    assert [(r["variant"], r["quantity"]) for r in got["order"]["lines"]] == [("L", 1)]
    b_client, b_url, _ = shop["portals"]["Bernd"]
    order(b_client, b_url, camp, [{"article": polo["id"], "variant": "L", "quantity": 2}])
    admin = ok(c.get(f"{shop['url']}{camp['id']}/"))
    sums = {s["name"]: s for s in admin["sums"]}
    assert {v["variant"]: v["quantity"] for v in sums["Poloshirt"]["variants"]} == {
        "S": 0,
        "M": 0,
        "L": 3,
        "XL": 0,
    }
    assert sums["Poloshirt"]["amount"] == "75.00"
    assert [o["name"] for o in admin["orders"]] == ["Anna Muster", "Bernd Muster"]
    # Zurückziehen
    ok(client.delete(f"{url}{camp['id']}/order/"))
    assert MemberOrder.objects.filter(campaign_id=camp["id"]).count() == 1
    # Excel mit Summen und Bestellungen
    resp = c.get(f"{shop['url']}{camp['id']}/export/")
    assert resp.status_code == 200 and resp.content[:2] == b"PK"


def test_pruefungen_auswahl_hoechstmengen_frist(c, shop):
    camp = new_campaign(c, shop)
    publish(c, shop, camp)
    polo, heft = camp["articles"]
    client, url, _ = shop["portals"]["Anna"]
    # Größe fehlt oder gibt es nicht
    order(client, url, camp, [{"article": polo["id"], "quantity": 1}], code=400)
    order(client, url, camp, [{"article": polo["id"], "variant": "XXS", "quantity": 1}], code=400)
    # höchstens 3 je Mitglied (über alle Größen)
    order(
        client,
        url,
        camp,
        [
            {"article": polo["id"], "variant": "M", "quantity": 2},
            {"article": polo["id"], "variant": "L", "quantity": 2},
        ],
        code=400,
    )
    # Gesamtmenge 3 Festschriften
    order(client, url, camp, [{"article": heft["id"], "quantity": 2}])
    b_client, b_url, _ = shop["portals"]["Bernd"]
    resp = order(b_client, b_url, camp, [{"article": heft["id"], "quantity": 2}], code=400)
    assert "1" in str(resp)
    order(b_client, b_url, camp, [{"article": heft["id"], "quantity": 1}])
    assert ok(client.get(f"{url}{camp['id']}/"))["articles"][1]["left"] == 0
    # Nach der Frist: Mitglied nicht mehr, Verwaltung schon
    OrderCampaign.objects.filter(pk=camp["id"]).update(
        deadline=timezone.localdate() - datetime.timedelta(days=1)
    )
    detail = ok(client.get(f"{url}{camp['id']}/"))
    assert detail["state"] == "closed" and detail["can_order"] is False
    order(client, url, camp, [{"article": heft["id"], "quantity": 1}], code=400)
    anna = shop["people"]["Anna"]
    ok(
        c.put(
            f"{shop['url']}{camp['id']}/orders/",
            {"membership": anna.pk, "lines": [{"article": heft["id"], "quantity": 1}]},
            content_type=JSON,
        )
    )


def test_groessenabfrage_ohne_preis_und_verein_zahlt(c, shop):
    # Reine Größenabfrage: keine Preise, keine Rechnung
    camp = new_campaign(
        c,
        shop,
        title="Größen für Uniformjacken",
        articles=[
            {"name": "Uniformjacke", "variants": ["48", "50", "52"], "variant_label": "Größe"}
        ],
    )
    publish(c, shop, camp)
    client, url, _ = shop["portals"]["Carla"]
    got = order(
        client, url, camp, [{"article": camp["articles"][0]["id"], "variant": "50", "quantity": 1}]
    )
    assert got["order"]["total"] is None
    admin = ok(c.post(f"{shop['url']}{camp['id']}/invoices/", {}, content_type=JSON))
    assert admin["created"] == 0 and not Invoice.objects.exists()
    # Verein zahlt: Mitglieder sehen keine Preise, Rechnungen gehen nicht
    paid = new_campaign(c, shop, title="T-Shirts zum Jubiläum", club_pays=True)
    publish(c, shop, paid)
    detail = ok(client.get(f"{url}{paid['id']}/"))
    assert detail["club_pays"] is True
    assert all(a["price"] is None for a in detail["articles"])
    got = order(client, url, paid, [{"article": paid["articles"][1]["id"], "quantity": 1}])
    assert got["order"]["total"] is None
    resp = c.post(f"{shop['url']}{paid['id']}/invoices/", {}, content_type=JSON)
    assert resp.status_code == 400
    assert ok(c.get(f"{shop['url']}{paid['id']}/"))["can_invoice"] is False


def test_rechnung_je_bestellung_und_ausgabe(c, shop):
    camp = new_campaign(c, shop)
    publish(c, shop, camp)
    polo, heft = camp["articles"]
    client, url, _ = shop["portals"]["Anna"]
    order(
        client,
        url,
        camp,
        [
            {"article": polo["id"], "variant": "M", "quantity": 2},
            {"article": heft["id"], "quantity": 1},
        ],
    )
    admin = ok(c.post(f"{shop['url']}{camp['id']}/invoices/", {}, content_type=JSON))
    assert admin["created"] == 1
    inv = Invoice.objects.get()
    assert inv.membership_id == shop["people"]["Anna"].pk
    assert inv.total == Decimal("60.00") and inv.status == "open"
    assert inv.subject == "Bestellung Vereinskleidung 2027"
    texts = list(inv.lines.order_by("position").values_list("text", flat=True))
    assert texts == ["2 × Vereinskleidung 2027: Poloshirt", "1 × Vereinskleidung 2027: Festschrift"]
    # Zweiter Lauf legt nichts doppelt an
    assert ok(c.post(f"{shop['url']}{camp['id']}/invoices/", {}, content_type=JSON))["created"] == 0
    # Mit Rechnung: Mitglied kann nicht mehr ändern
    detail = ok(client.get(f"{url}{camp['id']}/"))
    assert detail["can_order"] is False and detail["order"]["invoice"]["number"]
    order(client, url, camp, [{"article": heft["id"], "quantity": 1}], code=400)
    # Ausgabe abhaken
    order_id = admin["orders"][0]["id"]
    admin = ok(
        c.patch(
            f"{shop['url']}{camp['id']}/orders/{order_id}/",
            {"handed_out": True},
            content_type=JSON,
        )
    )
    assert admin["orders"][0]["handed_out"] is True


def test_untereinheit_rechte_modul_und_fremder_verein(c, shop, zug, orgs, api, club):
    camp = new_campaign(c, shop, department=zug.pk)
    publish(c, shop, camp)
    a_client, a_url, _ = shop["portals"]["Anna"]
    b_client, b_url, _ = shop["portals"]["Bernd"]
    assert [r["id"] for r in ok(a_client.get(a_url))["campaigns"]] == [camp["id"]]
    assert ok(b_client.get(b_url))["campaigns"] == []
    assert b_client.get(f"{b_url}{camp['id']}/").status_code == 404
    assert ok(c.get(f"{shop['url']}{camp['id']}/"))["audience"] == 1
    # Nur sehen: nichts anlegen
    leser = make_user("leser-bestellung@example.org")
    give_role(leser, club, permissions=["orders.view"], name="Bestell-Leser")
    assert api(leser).post(shop["url"], {"title": "x"}, content_type=JSON).status_code == 403
    assert ok(api(leser).get(shop["url"]))["can_edit"] is False
    # Bearbeiten ohne Rechnungsrecht: keine Rechnungen
    team = make_user("team-bestellung@example.org")
    give_role(team, club, permissions=["orders.view", "orders.edit"], name="Bestell-Team")
    assert ok(api(team).get(f"{shop['url']}{camp['id']}/"))["can_invoice"] is False
    assert api(team).post(f"{shop['url']}{camp['id']}/invoices/", {}).status_code == 403
    # Fremder Verein und Modul aus
    fremd = make_user("fremd-bestellung@example.org")
    give_role(fremd, orgs["b"], permissions=["orders.view", "orders.edit"], name="Fremd")
    assert api(fremd).get(shop["url"]).status_code == 404
    club.enabled_modules = sorted(set(club.enabled_modules) - {"orders"})
    club.save()
    assert c.get(shop["url"]).status_code == 404
    assert a_client.get(a_url).status_code == 404


def test_artikel_aendern_schuetzt_bestelltes_und_hinweis(c, shop):
    from portal.views import portal_summary

    camp = new_campaign(c, shop)
    _client, _url, access = shop["portals"]["Carla"]
    assert portal_summary(access)["orders_open"] == 0
    publish(c, shop, camp)
    summary = portal_summary(access)
    assert summary["orders_enabled"] is True and summary["orders_open"] == 1
    client, url, _ = shop["portals"]["Carla"]
    polo, heft = camp["articles"]
    order(client, url, camp, [{"article": polo["id"], "variant": "S", "quantity": 1}])
    assert portal_summary(access)["orders_open"] == 0
    detail_url = f"{shop['url']}{camp['id']}/"
    # Bestellte Größe bleibt, bestellter Artikel bleibt
    resp = c.patch(
        detail_url,
        {"articles": [{**polo, "variants": ["M", "L"]}, heft]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    resp = c.patch(detail_url, {"articles": [heft]}, content_type=JSON)
    assert resp.status_code == 400
    # Neue Größe und neuer Artikel gehen, unbestellter Artikel lässt sich löschen
    data = ok(
        c.patch(
            detail_url,
            {
                "articles": [
                    {**polo, "variants": ["S", "M", "L", "XL", "XXL"]},
                    {"name": "Kappe", "price": "8.50"},
                ]
            },
            content_type=JSON,
        )
    )
    assert [a["name"] for a in data["articles"]] == ["Poloshirt", "Kappe"]
    assert data["articles"][0]["variants"][-1] == "XXL"
    # Vorzeitig beenden und wieder öffnen
    assert publish(c, shop, camp, "close")["state"] == "closed"
    assert publish(c, shop, camp, "reopen")["state"] == "open"


def test_verwaltung_traegt_ein_und_ausgetretene(c, shop, club):
    camp = new_campaign(c, shop)
    publish(c, shop, camp)
    polo = camp["articles"][0]
    found = ok(c.get(f"{shop['url']}{camp['id']}/members/?q=bern"))["members"]
    assert [m["name"] for m in found] == ["Bernd Muster"]
    bernd = shop["people"]["Bernd"]
    data = ok(
        c.put(
            f"{shop['url']}{camp['id']}/orders/",
            {
                "membership": bernd.pk,
                "lines": [{"article": polo["id"], "variant": "XL", "quantity": 1}],
            },
            content_type=JSON,
        )
    )
    assert data["orders"][0]["entered_by_board"] is True
    # Fremde Mitgliedschaft geht nicht
    other = make_member(club, "Olaf", "Alt")
    with tenant_context(club.pk):
        MembershipPeriod.objects.filter(membership=other).update(
            exit_date=timezone.localdate() - datetime.timedelta(days=3), exit_reason="exit"
        )
    resp = c.put(
        f"{shop['url']}{camp['id']}/orders/",
        {"membership": other.pk, "lines": [{"article": polo["id"], "variant": "M", "quantity": 1}]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Löschen der ganzen Sammelbestellung
    assert c.delete(f"{shop['url']}{camp['id']}/").status_code == 204
    assert not MemberOrder.objects.exists()


def test_aufraeumen_nach_zwei_jahren(c, shop):
    from orders.services import purge_due

    camp = new_campaign(c, shop)
    OrderCampaign.objects.filter(pk=camp["id"]).update(
        deadline=timezone.localdate() - datetime.timedelta(days=800)
    )
    assert purge_due() == 1
    assert not OrderCampaign.objects.exists()
