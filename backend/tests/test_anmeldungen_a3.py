# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Anmeldung Stufe A3 (konzepte/veranstaltungen-anmeldung-gebuehr.md): Warteliste mit
Nachrücken, Stornostaffel mit Bearbeitungsgebühr, Teilabmeldung, Ersatzperson, Absage des
Termins, Verfall unbezahlter Anmeldungen. Alle Daten erfunden."""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from billing.models import Invoice
from core.tenancy import tenant_context
from registrations.models import Participant, Registration, RegistrationSetup

from .test_anmeldungen import JSON, einrichten, fest, ok, prices  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


def anmelden(fest, who, persons):
    client, url = fest["portals"][who]
    return client.post(f"{url}registration/", {"persons": persons}, content_type=JSON)


def tarife(fest, who="Bernd"):
    client, url = fest["portals"][who]
    return [p["id"] for p in ok(client.get(f"{url}registration/"))["offer"]["prices"]]


def bezahlen(c, club, setup, invoice_id):
    resp = c.post(
        f"/api/orgs/{club.pk}/billing/invoices/{invoice_id}/payments/",
        {"date": timezone.localdate().isoformat(), "method": "transfer", "account": setup["bank"]},
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 200, resp.content


def test_warteliste_und_nachruecken(c, fest, club, django_capture_on_commit_callbacks):
    einrichten(c, fest, capacity=1, waitlist=True)
    adult = tarife(fest)[0]
    bernd = ok(anmelden(fest, "Bernd", [{"membership_id": fest["bernd"].pk, "price_id": adult}]))
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        anna = ok(anmelden(fest, "Anna", [{"membership_id": fest["anna"].pk, "price_id": adult}]))
    wait = anna["mine"][0]
    assert wait["status"] == "waiting" and wait["invoice"] is None
    assert wait["waitlist_position"] == 1 and wait["paid_state"] == "waiting"
    assert anna["offer"]["waiting"] == 1
    assert any("Warteliste" in m.subject for m in mail.outbox)
    board = ok(c.get(fest["url"]))
    assert [r["status"] for r in board["registrations"]] == ["registered", "waiting"]
    assert board["summary"]["waiting"] == 1
    # Bernd meldet sich ab (keine Staffel): Anna rückt nach und bekommt die Rechnung
    client, url = fest["portals"]["Bernd"]
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(client.post(f"{url}registration/{bernd['mine'][0]['id']}/cancel/"))
    client, url = fest["portals"]["Anna"]
    mine = ok(client.get(f"{url}registration/"))["mine"][0]
    assert mine["status"] == "registered" and mine["invoice"] is not None
    assert mine["moved_up_at"] and mine["free_cancel_until"] and mine["can_cancel"]
    assert any("Platz frei" in m.subject or "nachgerückt" in m.body for m in mail.outbox)
    # In den 48 Stunden nach dem Nachrücken kostenlos abmelden
    quote = ok(client.get(f"{url}registration/{mine['id']}/cancel/"))
    assert quote["free_reason"] == "moved_up" and quote["fee"] == "0.00"


def test_stornostaffel_mit_bearbeitungsgebuehr(c, fest, club, setup):
    # Termin in 40 Tagen: „weniger als 60 Tage vorher: 50 %“ greift, dazu 5 € Bearbeitung
    einrichten(c, fest, cancel_rules=[{"days": 60, "percent": 50}], cancel_fee_fixed="5.00")
    adult = tarife(fest)[0]
    reg = ok(anmelden(fest, "Bernd", [{"membership_id": fest["bernd"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    total = Decimal(reg["total"])
    client, url = fest["portals"]["Bernd"]
    quote = ok(client.get(f"{url}registration/{reg['id']}/cancel/"))
    fee = (total / 2 + 5).quantize(Decimal("0.01"))
    assert quote["percent"] == 50 and Decimal(quote["fee"]) == fee
    data = ok(client.post(f"{url}registration/{reg['id']}/cancel/"))
    mine = data["mine"][0]
    assert mine["status"] == "cancelled" and Decimal(mine["cancel_fee"]) == fee
    assert mine["fee_invoice"] is not None and Decimal(mine["fee_invoice"]["total"]) == fee
    with tenant_context(club.pk):
        assert Invoice.objects.get(pk=reg["invoice"]["id"]).status == "cancelled"
    assert Decimal(ok(c.get(fest["url"]))["summary"]["fees"]) == fee


def test_staffel_ohne_treffer_kostenlos_und_erlassen(c, fest, club):
    einrichten(c, fest, cancel_rules=[{"days": 10, "percent": 100}], cancel_fee_fixed="5.00")
    adult = tarife(fest)[0]
    reg = ok(anmelden(fest, "Bernd", [{"membership_id": fest["bernd"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    quote = ok(c.get(f"{fest['url']}{reg['id']}/cancel/"))
    assert quote["percent"] == 0 and quote["fee"] == "0.00"
    # Verwaltung: Erlassen nur mit Grund
    with tenant_context(club.pk):
        RegistrationSetup.objects.update(cancel_rules=[{"days": 60, "percent": 100}])
    assert ok(c.get(f"{fest['url']}{reg['id']}/cancel/"))["fee"] == reg["total"]
    resp = c.post(f"{fest['url']}{reg['id']}/cancel/", {"waive": True}, content_type=JSON)
    assert resp.status_code == 400
    data = ok(
        c.post(
            f"{fest['url']}{reg['id']}/cancel/",
            {"waive": True, "reason": "Krankheit"},
            content_type=JSON,
        )
    )
    row = data["registrations"][0]
    assert row["status"] == "cancelled" and row["cancel_fee"] == "0.00"


def test_teilabmeldung_mit_guthaben(c, fest, club, setup, django_capture_on_commit_callbacks):
    einrichten(c, fest)
    adult, kids, _guests = tarife(fest, "Anna")
    data = ok(
        anmelden(
            fest,
            "Anna",
            [
                {"membership_id": fest["anna"].pk, "price_id": adult},
                {"membership_id": fest["kind"].pk, "price_id": kids},
            ],
        )
    )
    reg = data["mine"][0]
    bezahlen(c, club, setup, reg["invoice"]["id"])
    kim = next(p for p in reg["participants"] if p["name"] == "Kim Muster")
    client, url = fest["portals"]["Anna"]
    quote = ok(client.get(f"{url}registration/{reg['id']}/cancel/?participants={kim['id']}"))
    assert quote["base"] == "15.00" and quote["fee"] == "0.00"
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        data = ok(
            client.post(
                f"{url}registration/{reg['id']}/cancel/",
                {"participants": [kim["id"]]},
                content_type=JSON,
            )
        )
    mine = data["mine"][0]
    assert mine["status"] == "registered"
    assert Decimal(mine["total"]) == Decimal(reg["total"]) - 15
    assert mine["invoice"]["id"] != reg["invoice"]["id"]
    with tenant_context(club.pk):
        old = Invoice.objects.get(pk=reg["invoice"]["id"])
        new = Invoice.objects.get(pk=mine["invoice"]["id"])
        assert old.status == "cancelled" and new.total == Decimal(mine["total"])
        # Gezahlt war mehr als die neue Rechnung: Guthaben bleibt zum Erstatten
        assert old.paid == Decimal(reg["total"])
        assert Participant.objects.filter(status="cancelled").count() == 1
    assert any("Abmeldung" in m.subject for m in mail.outbox)
    # Fremde Person in der Liste: abgelehnt
    resp = client.post(
        f"{url}registration/{reg['id']}/cancel/", {"participants": [999999]}, content_type=JSON
    )
    assert resp.status_code == 400


def test_teilabmeldung_verrechnet_guthaben_mit_gebuehr(c, fest, club, setup):
    # Unbezahlt, 100 % Staffel: neue Rechnung = übrige Person + Gebühr für Kim
    einrichten(c, fest, cancel_rules=[{"days": 60, "percent": 100}])
    adult, kids, _guests = tarife(fest, "Anna")
    reg = ok(
        anmelden(
            fest,
            "Anna",
            [
                {"membership_id": fest["anna"].pk, "price_id": adult},
                {"membership_id": fest["kind"].pk, "price_id": kids},
            ],
        )
    )["mine"][0]
    bezahlen(c, club, setup, reg["invoice"]["id"])
    kim = next(p for p in reg["participants"] if p["name"] == "Kim Muster")
    data = ok(
        c.post(
            f"{fest['url']}{reg['id']}/cancel/",
            {"participants": [kim["id"]], "reason": "krank"},
            content_type=JSON,
        )
    )
    row = data["registrations"][0]
    assert row["cancel_fee"] == "15.00"
    with tenant_context(club.pk):
        new = Invoice.objects.get(pk=row["invoice"]["id"])
        # Gesamtbetrag bleibt gleich, das Geld wandert an die neue Rechnung
        assert new.total == Decimal(reg["total"]) and new.paid == new.total
        assert Invoice.objects.get(pk=reg["invoice"]["id"]).paid == 0


def test_ersatzperson(c, fest, club):
    einrichten(c, fest)
    adult, _kids, guests = tarife(fest, "Anna")
    reg = ok(anmelden(fest, "Anna", [{"membership_id": fest["anna"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    assert reg["can_substitute"]
    p = reg["participants"][0]
    client, url = fest["portals"]["Anna"]
    data = ok(
        client.post(
            f"{url}registration/{reg['id']}/participants/{p['id']}/",
            {"name": "Erna Ersatz", "birth_date": "1980-03-04"},
            content_type=JSON,
        )
    )
    q = data["mine"][0]["participants"][0]
    assert q["name"] == "Erna Ersatz" and q["amount"] == p["amount"] and q["membership_id"] is None
    # Fremdes Mitglied geht im Mitgliederbereich nicht
    resp = client.post(
        f"{url}registration/{reg['id']}/participants/{p['id']}/",
        {"membership_id": fest["bernd"].pk},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Ohne Ersatzpersonen: Mitglied abgelehnt, Verwaltung darf
    with tenant_context(club.pk):
        RegistrationSetup.objects.update(substitute_allowed=False)
    resp = client.post(
        f"{url}registration/{reg['id']}/participants/{p['id']}/",
        {"name": "Otto Ersatz", "birth_date": "1981-05-06"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    data = ok(
        c.post(
            f"{fest['url']}{reg['id']}/participants/{p['id']}/",
            {"membership_id": fest["bernd"].pk},
            content_type=JSON,
        )
    )
    assert data["registrations"][0]["participants"][0]["name"] == "Bernd Beispiel"


def test_absage_hebt_alles_ohne_gebuehr_auf(c, fest, club, django_capture_on_commit_callbacks):
    einrichten(c, fest, capacity=1, waitlist=True, cancel_rules=[{"days": 60, "percent": 100}])
    adult = tarife(fest)[0]
    reg = ok(anmelden(fest, "Bernd", [{"membership_id": fest["bernd"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    ok(anmelden(fest, "Anna", [{"membership_id": fest["anna"].pk, "price_id": adult}]))
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(
            c.patch(
                f"{fest['org']}/events/{fest['event']['id']}/",
                {"is_cancelled": True},
                content_type=JSON,
            )
        )
    with tenant_context(club.pk):
        assert set(Registration.objects.values_list("status", flat=True)) == {"cancelled"}
        assert Registration.objects.filter(cancel_fee__gt=0).count() == 0
        assert Invoice.objects.get(pk=reg["invoice"]["id"]).status == "cancelled"
    assert len([m for m in mail.outbox if m.subject.startswith("Abgesagt: Vereinsausflug")]) >= 2


def test_unbezahlte_verfallen_und_warteliste_endet(c, fest, club, setup):
    from registrations.services import close_waitlists, expire_due

    einrichten(c, fest, capacity=2, waitlist=True, expire_unpaid_days=7)
    adult = tarife(fest)[0]
    bernd = ok(anmelden(fest, "Bernd", [{"membership_id": fest["bernd"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    anna = ok(anmelden(fest, "Anna", [{"membership_id": fest["anna"].pk, "price_id": adult}]))[
        "mine"
    ][0]
    bezahlen(c, club, setup, anna["invoice"]["id"])
    # Platz 3 wartet: Gast über die Verwaltung
    guests = tarife(fest)[2]
    ok(
        c.post(
            f"{fest['url']}list/",
            {"name": "Greta Gast", "persons": [{"name": "Greta Gast", "price_id": guests}]},
            content_type=JSON,
        )
    )
    assert expire_due() == 0
    later = timezone.now() + datetime.timedelta(days=35)
    assert expire_due(later) == 1
    with tenant_context(club.pk):
        assert Registration.objects.get(pk=bernd["id"]).status == "cancelled"
        assert Registration.objects.get(pk=anna["id"]).status == "registered"
        greta = Registration.objects.exclude(pk__in=[bernd["id"], anna["id"]]).get()
        # expire_due läuft mit „later“, move_up mit echter Zeit: Greta rückt nach
        assert greta.status == "registered"
        greta.status = "waiting"
        greta.save(update_fields=["status"])
    assert close_waitlists() == 0
    assert close_waitlists(timezone.now() + datetime.timedelta(days=41)) == 1
    with tenant_context(club.pk):
        assert Registration.objects.get(pk=greta.pk).status == "cancelled"


def test_staffel_pruefung(c, fest):
    bad = [{"days": 10, "percent": 50}, {"days": 10, "percent": 80}]
    resp = c.put(
        fest["url"],
        {"closes_at": fest["event"]["starts_at"], "prices": prices(), "cancel_rules": bad},
        content_type=JSON,
    )
    assert resp.status_code == 400
    data = einrichten(
        c, fest, cancel_rules=[{"days": 7, "percent": 100}, {"days": 30, "percent": 50}]
    )
    assert [r["days"] for r in data["offer"]["cancel_rules"]] == [30, 7]
