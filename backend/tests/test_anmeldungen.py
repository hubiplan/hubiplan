# ruff: noqa: F811  (Fixtures aus test_m9_billing)
"""Verbindliche Anmeldung mit Teilnahmegebühr (konzepte/veranstaltungen-anmeldung-gebuehr.md,
Stufen A1 und A2): Tarife mit Preisstufen, Plätze, Anmeldung durch Mitglieder und Verwaltung,
Rechnung, Zahlungseingang, Abmeldung."""

import datetime
import uuid

import pytest
from django.core import mail
from django.utils import timezone

from billing.models import Invoice
from core.tenancy import tenant_context
from members.models import Household, HouseholdMember
from registrations.models import Participant, Registration

from .factories import give_role, make_member, make_user
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def soon(days):
    return (timezone.now() + datetime.timedelta(days=days)).isoformat()


@pytest.fixture
def fest(club, c, setup, api):
    from portal.models import PortalAccess

    club.enabled_modules = sorted(
        {*club.enabled_modules, "events", "portal", "registrations", "finance", "billing"}
    )
    club.save()
    org = f"/api/orgs/{club.pk}"
    event = ok(
        c.post(
            f"{org}/events/",
            {"title": "Vereinsausflug", "starts_at": soon(40), "ends_at": soon(40.3)},
            content_type=JSON,
        )
    )
    anna = make_member(club, "Anna", "Muster", "anna@example.org")
    kind = make_member(
        club, "Kim", "Muster", birth_date=timezone.localdate() - datetime.timedelta(days=365 * 9)
    )
    bernd = make_member(club, "Bernd", "Beispiel", "bernd@example.org")
    with tenant_context(club.pk):
        home = Household.objects.create(organization=club, name="Muster", kind="family")
        for m in (anna, kind):
            HouseholdMember.objects.create(
                organization=club,
                household=home,
                membership=m,
                kind="family",
                valid_from=datetime.date(2020, 1, 1),
            )
    portals = {}
    for m in (anna, bernd):
        user = make_user(f"{m.person.first_name.lower()}-konto@example.org")
        access = PortalAccess.objects.create(organization=club, membership=m, user=user)
        portals[m.person.first_name] = (api(user), f"/api/portal/{access.pk}/events/{event['id']}/")
    return {
        "org": org,
        "event": event,
        "url": f"{org}/events/{event['id']}/registration/",
        "anna": anna,
        "kind": kind,
        "bernd": bernd,
        "portals": portals,
        "category": setup["cat"] if "cat" in setup else None,
    }


def prices(early_until=None, early_count=None):
    return [
        {
            "name": "Erwachsene",
            "applies": "all",
            "age_from": 15,
            "steps": [
                {
                    "name": "Early Bird",
                    "amount": "29.00",
                    "until_date": early_until,
                    "until_count": early_count,
                },
                {"name": "Normal", "amount": "35.00"},
            ],
        },
        {"name": "Kinder bis 14", "age_to": 14, "steps": [{"amount": "15.00"}]},
        {"name": "Gäste", "applies": "guests", "steps": [{"amount": "40.00"}]},
    ]


def einrichten(c, fest, **extra):
    data = {"closes_at": soon(30), "capacity": 5, "prices": prices(), **extra}
    return ok(c.put(fest["url"], data, content_type=JSON))


def test_einrichten_mit_preisstufen_und_finanzveranstaltung(c, fest):
    data = einrichten(c, fest, prices=prices(early_count=1))
    offer = data["offer"]
    assert offer["state"] == "open" and offer["free"] == 5
    adult = offer["prices"][0]
    assert adult["current"]["name"] == "Early Bird" and adult["current"]["amount"] == "29.00"
    assert adult["current"]["remaining"] == 1 and adult["next"]["amount"] == "35.00"
    # Termin zeigt die Anmeldung, Zu- und Absagen lassen sich nicht mehr einschalten
    event = ok(c.get(f"{fest['org']}/events/{fest['event']['id']}/"))
    assert event["registration"]["enabled"] and event["project"] is not None
    resp = c.patch(
        f"{fest['org']}/events/{fest['event']['id']}/", {"rsvp_enabled": True}, content_type=JSON
    )
    assert resp.status_code == 400


def test_letzte_stufe_ohne_grenze(c, fest):
    bad = prices()
    bad[1]["steps"][0]["until_count"] = 3
    resp = c.put(fest["url"], {"closes_at": soon(30), "prices": bad}, content_type=JSON)
    assert resp.status_code == 400


def test_preise_nur_mit_rechnungsrecht(club, fest, api, c):
    user = make_user("termine@example.org")
    give_role(
        user,
        club,
        permissions=["events.view", "events.edit", "registrations.view", "registrations.edit"],
        name="Termine",
    )
    resp = api(user).put(
        fest["url"], {"closes_at": soon(30), "prices": prices()}, content_type=JSON
    )
    assert resp.status_code == 403
    free = [{"name": "Alle", "steps": [{"amount": "0"}]}]
    ok(api(user).put(fest["url"], {"closes_at": soon(30), "prices": free}, content_type=JSON))


def test_mitglied_meldet_sich_und_kind_an_rechnung_und_bestaetigung(
    c, fest, django_capture_on_commit_callbacks
):
    einrichten(c, fest, prices=prices(early_count=1))
    client, url = fest["portals"]["Anna"]
    offer = ok(client.get(f"{url}registration/"))
    names = {p["name"] for p in offer["persons"]}
    assert names == {"Anna Muster", "Kim Muster"}
    adult, kids, guests = (p["id"] for p in offer["offer"]["prices"])
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        data = ok(
            client.post(
                f"{url}registration/",
                {
                    "persons": [
                        {"membership_id": fest["anna"].pk, "price_id": adult},
                        {"membership_id": fest["kind"].pk, "price_id": kids},
                        {"name": "Gerd Gast", "price_id": guests},
                    ]
                },
                content_type=JSON,
            ),
            201,
        )
    mine = data["mine"][0]
    assert mine["total"] == "84.00" and mine["paid_state"] == "open"
    assert [p["amount"] for p in mine["participants"]] == ["29.00", "15.00", "40.00"]
    assert data["offer"]["free"] == 2
    # Early Bird war nur für einen Platz: jetzt gilt Normal
    assert data["offer"]["prices"][0]["current"]["name"] == "Normal"
    with tenant_context(fest["anna"].organization_id):
        inv = Invoice.objects.get(pk=mine["invoice"]["id"])
        assert inv.status == "open" and inv.total == 84 and inv.recipient_kind == "member"
        assert inv.project_id is not None and inv.lines.count() == 3
    sent = [m for m in mail.outbox if "Anmeldebestätigung" in m.subject]
    assert len(sent) == 1
    names = [a[0] for a in sent[0].attachments]
    assert any(n.endswith(".pdf") for n in names) and "termin.ics" in names
    # Schon angemeldet: noch einmal geht nicht
    resp = client.post(
        f"{url}registration/",
        {"persons": [{"membership_id": fest["anna"].pk, "price_id": adult}]},
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_tarifbedingungen_und_plaetze(c, fest):
    einrichten(c, fest, capacity=2)
    client, url = fest["portals"]["Bernd"]
    adult, kids, guests = (
        p["id"] for p in ok(client.get(f"{url}registration/"))["offer"]["prices"]
    )
    # Gästetarif nicht für Mitglieder
    resp = client.post(
        f"{url}registration/",
        {"persons": [{"membership_id": fest["bernd"].pk, "price_id": guests}]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Fremdes Mitglied (nicht in der Familie) darf Bernd nicht anmelden
    resp = client.post(
        f"{url}registration/",
        {"persons": [{"membership_id": fest["anna"].pk, "price_id": adult}]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Drei Personen bei zwei Plätzen
    resp = client.post(
        f"{url}registration/",
        {
            "persons": [
                {"membership_id": fest["bernd"].pk, "price_id": adult},
                {"name": "Gast Eins", "price_id": guests},
                {"name": "Gast Zwei", "price_id": guests},
            ]
        },
        content_type=JSON,
    )
    assert resp.status_code == 400 and "2" in resp.content.decode()


def test_zahlung_bestaetigt_und_abmeldung_storniert(
    c, fest, setup, club, django_capture_on_commit_callbacks
):
    einrichten(c, fest)
    client, url = fest["portals"]["Bernd"]
    adult = ok(client.get(f"{url}registration/"))["offer"]["prices"][0]["id"]
    data = ok(
        client.post(
            f"{url}registration/",
            {"persons": [{"membership_id": fest["bernd"].pk, "price_id": adult}]},
            content_type=JSON,
        )
    )
    reg = data["mine"][0]
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = c.post(
            f"/api/orgs/{club.pk}/billing/invoices/{reg['invoice']['id']}/payments/",
            {
                "date": timezone.localdate().isoformat(),
                "method": "transfer",
                "account": setup["bank"],
            },
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
    assert resp.status_code == 200, resp.content
    assert [m.subject for m in mail.outbox if "Zahlung eingegangen" in m.subject]
    board = ok(c.get(fest["url"]))
    assert board["registrations"][0]["paid_state"] == "paid"
    assert board["summary"]["paid"] == reg["total"]
    # Abmelden vor dem Anmeldeschluss: Stornorechnung, Hinweis auf Erstattung
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        data = ok(client.post(f"{url}registration/{reg['id']}/cancel/"))
    assert data["mine"][0]["status"] == "cancelled"
    with tenant_context(club.pk):
        assert Invoice.objects.get(pk=reg["invoice"]["id"]).status == "cancelled"
        assert Participant.objects.filter(status="active").count() == 0
    sent = [m for m in mail.outbox if "Abmeldung" in m.subject]
    assert sent and "erstatten" in sent[0].body
    assert ok(client.get(f"{url}registration/"))["offer"]["free"] == 5


def test_verwaltung_meldet_gast_an_rechnung_an_teilnehmende(c, fest, club):
    einrichten(c, fest)
    guests = ok(c.get(fest["url"]))["offer"]["prices"][2]["id"]
    data = ok(
        c.post(
            f"{fest['url']}list/",
            {
                "name": "Greta Gast",
                "email": "greta@example.org",
                "address": "Musterweg 1\n12345 Musterstadt",
                "persons": [{"name": "Greta Gast", "price_id": guests}],
            },
            content_type=JSON,
        ),
        201,
    )
    reg = data["registrations"][0]
    assert reg["number"].startswith("A") and reg["source"] == "board"
    with tenant_context(club.pk):
        inv = Invoice.objects.get(pk=reg["invoice"]["id"])
        assert inv.recipient_kind == "registration" and inv.membership_id is None
        assert inv.recipient_name == "Greta Gast"
    xlsx = c.get(f"{fest['url']}export/")
    assert xlsx.status_code == 200 and xlsx["Content-Type"].startswith("application/vnd")
    # Termin mit Anmeldungen lässt sich nicht löschen
    resp = c.delete(f"{fest['org']}/events/{fest['event']['id']}/")
    assert resp.status_code == 400


def test_kostenlos_ohne_rechnung_und_nach_schluss_kein_abmelden(c, fest, club):
    free = [{"name": "Alle", "steps": [{"amount": "0"}]}]
    einrichten(c, fest, prices=free)
    client, url = fest["portals"]["Bernd"]
    price = ok(client.get(f"{url}registration/"))["offer"]["prices"][0]["id"]
    data = ok(
        client.post(
            f"{url}registration/",
            {"persons": [{"membership_id": fest["bernd"].pk, "price_id": price}]},
            content_type=JSON,
        )
    )
    reg = data["mine"][0]
    assert reg["invoice"] is None and reg["paid_state"] == "free"
    with tenant_context(club.pk):
        Registration.objects.filter(pk=reg["id"]).update()
        from registrations.models import RegistrationSetup

        RegistrationSetup.objects.update(closes_at=timezone.now() - datetime.timedelta(hours=1))
    assert client.post(f"{url}registration/{reg['id']}/cancel/").status_code == 400
    # Nach dem Anmeldeschluss nimmt der Mitgliederbereich keine Anmeldung mehr an
    resp = client.post(
        f"{url}registration/",
        {"persons": [{"name": "Gast", "price_id": price}]},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Die Verwaltung kann trotzdem abmelden
    ok(c.post(f"{fest['url']}{reg['id']}/cancel/", {"reason": "krank"}, content_type=JSON))


def test_daten_von_gaesten_werden_spaeter_geloescht(c, fest, club):
    from registrations.services import purge_due

    einrichten(c, fest)
    guests = ok(c.get(fest["url"]))["offer"]["prices"][2]["id"]
    ok(
        c.post(
            f"{fest['url']}list/",
            {"name": "Greta Gast", "persons": [{"name": "Greta Gast", "price_id": guests}]},
            content_type=JSON,
        )
    )
    assert purge_due() == 0
    assert purge_due(timezone.now() + datetime.timedelta(days=400)) == 1
    with tenant_context(club.pk):
        reg = Registration.objects.get()
        assert reg.name != "Greta Gast" and reg.participants.get().name != "Greta Gast"
