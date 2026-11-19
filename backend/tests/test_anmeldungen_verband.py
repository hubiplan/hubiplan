"""Sammelanmeldung der Vereine zu einem Termin ihres Dachverbands
(konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A8). Alle Daten erfunden."""

import datetime

import pytest
from django.utils import timezone

from billing.models import Invoice
from core.tenancy import tenant_context
from registrations.models import Participant, Registration

from .factories import give_role, make_member, make_user
from .test_anmeldungen import JSON, ok, soon

pytestmark = pytest.mark.django_db

PRICES = [
    {"name": "Lehrgang", "applies": "members", "steps": [{"amount": "60.00"}]},
]


@pytest.fixture
def verband(orgs, api):
    fed, club = orgs["federation"], orgs["a"]
    fed.enabled_modules = ["members", "events", "finance", "billing", "registrations"]
    fed.save()
    for org in (club, orgs["b"]):
        # Der Verein braucht das Modul Anmeldungen (Recht registrations.edit)
        org.enabled_modules = ["members", "events", "registrations"]
        org.save()
    fed_user = make_user("vorstand-bund@example.org")
    give_role(fed_user, fed)
    club_user = make_user("vorstand-a@example.org")
    give_role(club_user, club)
    f, c = api(fed_user), api(club_user)
    fin = f"/api/orgs/{fed.pk}/finance"
    bank = ok(
        f.post(
            f"{fin}/accounts/",
            {
                "name": "Girokonto",
                "iban": "DE89370400440532013000",
                "bic": "COBADEFFXXX",
                "opening_date": "2025-01-01",
            },
            content_type=JSON,
        )
    )["id"]
    cat = ok(
        f.post(f"{fin}/categories/", {"name": "Lehrgänge", "kind": "income"}, content_type=JSON)
    )["id"]
    ok(
        f.patch(
            f"/api/orgs/{fed.pk}/billing/settings/",
            {"account": bank, "category": cat},
            content_type=JSON,
        )
    )
    event = ok(
        f.post(
            f"/api/orgs/{fed.pk}/events/",
            {"title": "Lehrgang Standaufsicht", "starts_at": soon(40), "ends_at": soon(40.3)},
            content_type=JSON,
        )
    )
    url = f"/api/orgs/{fed.pk}/events/{event['id']}/registration/"
    ok(
        f.put(
            url,
            {"closes_at": soon(30), "prices": PRICES, "club_registration": True},
            content_type=JSON,
        )
    )
    anna = make_member(club, "Anna", "Muster", "anna@example.org")
    bernd = make_member(
        club,
        "Bernd",
        "Beispiel",
        birth_date=timezone.localdate() - datetime.timedelta(days=365 * 40),
    )
    return {
        "fed": fed,
        "club": club,
        "f": f,
        "c": c,
        "event": event,
        "url": url,
        "club_url": f"/api/orgs/{club.pk}/events/{event['id']}/registration/club/",
        "anna": anna,
        "bernd": bernd,
    }


def test_nur_beim_dachverband(orgs, api):
    club = orgs["c"]
    club.enabled_modules = ["members", "events", "registrations"]
    club.save()
    user = make_user("vorstand-c@example.org")
    give_role(user, club)
    c = api(user)
    event = ok(
        c.post(
            f"/api/orgs/{club.pk}/events/",
            {"title": "Ausflug", "starts_at": soon(40)},
            content_type=JSON,
        )
    )
    resp = c.put(
        f"/api/orgs/{club.pk}/events/{event['id']}/registration/",
        {
            "closes_at": soon(30),
            "prices": [{"name": "Alle", "steps": [{"amount": "0"}]}],
            "club_registration": True,
        },
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_verein_meldet_mitglieder_rechnung_an_den_verein(verband):
    v = verband
    c, f = v["c"], v["f"]
    detail = ok(c.get(f"/api/orgs/{v['club'].pk}/events/{v['event']['id']}/"))
    assert detail["registration"]["club_register"] is True
    data = ok(c.get(v["club_url"]))
    assert data["offer"]["club_registration"] and data["registrations"] == []
    price = data["offer"]["prices"][0]["id"]
    done = ok(
        c.post(
            v["club_url"],
            {
                "persons": [
                    {"membership_id": v["anna"].pk, "price_id": price},
                    {"membership_id": v["bernd"].pk, "price_id": price},
                ]
            },
            content_type=JSON,
        )
    )
    assert len(done["registrations"]) == 1
    assert sorted(done["registered_members"]) == sorted([v["anna"].pk, v["bernd"].pk])
    reg = done["registrations"][0]
    assert reg["total"] == "120.00" and reg["invoice"]
    # Noch einmal dieselbe Person: abgewiesen
    again = c.post(
        v["club_url"],
        {"persons": [{"membership_id": v["anna"].pk, "price_id": price}]},
        content_type=JSON,
    )
    assert again.status_code == 400
    # Beim Dachverband: Anmeldung des Vereins, Rechnung an den Verein
    with tenant_context(v["fed"].pk):
        r = Registration.objects.get(pk=reg["id"])
        assert r.club_id == v["club"].pk and r.source == Registration.Source.CLUB
        assert r.organization_id == v["fed"].pk and r.membership_id is None
        inv = Invoice.objects.get(pk=r.invoice_id)
        assert inv.recipient_kind == Invoice.Recipient.CLUB and inv.club_id == v["club"].pk
        assert inv.recipient_name == v["club"].name and inv.total == 120
        names = sorted(Participant.objects.filter(registration=r).values_list("name", flat=True))
    assert names == ["Anna Muster", "Bernd Beispiel"]
    board = ok(f.get(v["url"]))
    assert board["registrations"][0]["club_id"] == v["club"].pk
    # Abmelden einer Person durch den Verein
    anna_p = next(p for p in reg["participants"] if p["name"] == "Anna Muster")
    after = ok(
        c.post(
            f"{v['club_url']}{reg['id']}/cancel/",
            {"participants": [anna_p["id"]]},
            content_type=JSON,
        )
    )
    assert after["registered_members"] == [v["bernd"].pk]


def test_andere_vereine_und_ohne_recht(verband, orgs, api):
    v = verband
    other = make_user("vorstand-b@example.org")
    give_role(other, orgs["b"])
    b = api(other)
    data = ok(b.get(f"/api/orgs/{orgs['b'].pk}/events/{v['event']['id']}/registration/club/"))
    price = data["offer"]["prices"][0]["id"]
    ok(
        v["c"].post(
            v["club_url"],
            {"persons": [{"membership_id": v["anna"].pk, "price_id": price}]},
            content_type=JSON,
        )
    )
    # Verein B sieht die Anmeldung von Verein A nicht und kann keine Mitglieder von A melden
    data = ok(b.get(f"/api/orgs/{orgs['b'].pk}/events/{v['event']['id']}/registration/club/"))
    assert data["registrations"] == []
    resp = b.post(
        f"/api/orgs/{orgs['b'].pk}/events/{v['event']['id']}/registration/club/",
        {"persons": [{"membership_id": v["bernd"].pk, "price_id": price}]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Ohne Sammelanmeldung: nicht erreichbar
    ok(
        v["f"].put(
            v["url"],
            {"closes_at": soon(30), "prices": PRICES, "club_registration": False},
            content_type=JSON,
        )
    )
    assert v["c"].get(v["club_url"]).status_code == 404


def test_sammelanmeldungen_unter_meldungen(verband, orgs, api):
    v = verband
    offers_url = f"/api/orgs/{v['club'].pk}/registrations/club-offers/"
    data = ok(v["c"].get(offers_url))
    assert data["federation"] == v["fed"].name
    assert [o["event_id"] for o in data["offers"]] == [v["event"]["id"]]
    assert data["offers"][0]["persons"] == 0 and data["offers"][0]["state"] == "open"
    price = ok(v["c"].get(v["club_url"]))["offer"]["prices"][0]["id"]
    ok(
        v["c"].post(
            v["club_url"],
            {"persons": [{"membership_id": v["anna"].pk, "price_id": price}]},
            content_type=JSON,
        )
    )
    assert ok(v["c"].get(offers_url))["offers"][0]["persons"] == 1
    # Ohne Sammelanmeldung: nicht mehr in der Liste
    ok(
        v["f"].put(
            v["url"],
            {"closes_at": soon(30), "prices": PRICES, "club_registration": False},
            content_type=JSON,
        )
    )
    assert ok(v["c"].get(offers_url))["offers"] == []
