# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Gesamtaudit 19.11.2026, Block 1 (Anmeldung mit Teilnahmegebühr): Sammelanmeldung (S-01),
Bestätigungsmail (S-03), Scan- und Kassen-Links (S-04, S-05). Alle Daten erfunden."""

import datetime

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import rls_bypass, tenant_context
from registrations import notify, scanning
from registrations.models import Participant, ScanLink

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_anmeldungen_oeffentlich import _public, _send
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

FREE = [{"name": "Alle", "steps": [{"amount": "0"}]}]


def _sammelanmeldung(c, fest, *wer):
    """Die Verwaltung meldet mehrere Mitglieder in einer Anmeldung an; gebucht hat das erste."""
    price = ok(c.get(fest["url"]))["offer"]["prices"][0]["id"]
    resp = c.post(
        f"{fest['url']}list/",
        {
            "membership_id": fest[wer[0]].pk,
            "persons": [{"membership_id": fest[w].pk, "price_id": price} for w in wer],
        },
        content_type=JSON,
    )
    assert resp.status_code in (200, 201), resp.content


def test_mitangemeldete_sehen_nur_die_eigene_zeile(c, fest):
    """S-01: Bernd hat gebucht, Anna (nicht verwandt) ist nur dabei. Anna sieht ihre Zeile und
    lädt ihre Karte, nicht Bernds Angaben. Bernd sieht alles."""
    einrichten(c, fest, prices=FREE)
    _sammelanmeldung(c, fest, "bernd", "anna")
    anna, anna_url = fest["portals"]["Anna"]
    bernd, bernd_url = fest["portals"]["Bernd"]

    mine = ok(anna.get(f"{anna_url}registration/"))["mine"]
    assert len(mine) == 1
    reg = mine[0]
    assert [p["name"] for p in reg["participants"]] == ["Anna Muster"]
    assert reg["name"] == "Anna Muster" and "Bernd" not in str(reg)
    assert reg["invoice"] is None and reg["fee_invoice"] is None
    assert reg["answers"] == {} and reg["bookings"] == []
    assert reg["can_cancel"] is False and reg["can_substitute"] is False
    assert reg["booked_by_other"] is True and reg["has_tickets"] is True

    whole = ok(bernd.get(f"{bernd_url}registration/"))["mine"][0]
    assert sorted(p["name"] for p in whole["participants"]) == ["Anna Muster", "Bernd Beispiel"]
    assert "booked_by_other" not in whole

    # Karten: Anna bekommt nur ihre, Bernd beide (das PDF mit zwei Karten ist größer)
    own = anna.get(f"{anna_url}registration/{reg['id']}/tickets/")
    both = bernd.get(f"{bernd_url}registration/{reg['id']}/tickets/")
    assert own.status_code == 200 and both.status_code == 200
    assert own.content.startswith(b"%PDF") and len(own.content) < len(both.content)

    # Auch die Liste aller eigenen Anmeldungen (Apps) zeigt nur die eigene Zeile
    access = anna_url.split("/events/")[0]
    items = ok(anna.get(f"{access}/registrations/"))["items"]
    assert len(items) == 1 and "Bernd" not in str(items)
    assert [p["name"] for p in items[0]["participants"]] == ["Anna Muster"]

    # Abmelden und Ersatzperson bleiben der buchenden Person vorbehalten
    assert anna.post(f"{anna_url}registration/{reg['id']}/cancel/", {}, JSON).status_code == 404


def test_eltern_sehen_die_zeile_ihres_kindes(c, fest):
    """Bernd bucht für sich, Anna und Annas Kind Kim: Anna sieht sich und Kim, nicht Bernd."""
    einrichten(c, fest, prices=FREE)
    _sammelanmeldung(c, fest, "bernd", "anna", "kind")
    anna, anna_url = fest["portals"]["Anna"]
    reg = ok(anna.get(f"{anna_url}registration/"))["mine"][0]
    assert sorted(p["name"] for p in reg["participants"]) == ["Anna Muster", "Kim Muster"]


def test_auskunft_ohne_fremde_personen(c, fest, club):
    """Die Auskunft nach Art. 15 enthält bei Mitangemeldeten nur die eigene Zeile."""
    import io
    import zipfile

    from members import auskunft

    einrichten(c, fest, prices=FREE)
    _sammelanmeldung(c, fest, "bernd", "anna")
    with tenant_context(club.pk):
        packed = auskunft.build(fest["anna"], club)
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        name = next(n for n in z.namelist() if n.endswith("anmeldungen.json"))
        text = z.read(name).decode()
    assert "Anna Muster" in text and "Bernd" not in text


def test_bestaetigungsmail_ohne_fremden_text(c, fest, django_capture_on_commit_callbacks):
    """S-03: Die Mail an die noch unbestätigte Adresse trägt keinen frei eingegebenen Text."""
    data = _public(c, fest)
    key = data["offer"]["public_url"].rsplit("/", 1)[-1]
    form = ok(Client().get(f"/api/public/registration/{key}/"))
    guest = next(p for p in form["offer"]["prices"] if p["name"] == "Gäste")
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(
            _send(
                key,
                name="Gewinn abholen: https://boese.example.org/jetzt",
                persons=[
                    {"name": "www.boese.example.org besuchen", "price_id": guest["id"]},
                    {"name": "Max Beispiel", "price_id": guest["id"]},
                ],
            ),
            201,
        )
    sent = [m for m in mail.outbox if "Anmeldung bestätigen" in m.subject]
    assert sent
    body = sent[0].body
    assert "boese.example.org" not in body and "https://boese" not in body
    assert "www." not in body and "Max Beispiel" not in body
    assert "2 Personen" in body
    assert "/anmeldung/bestaetigen/" in body


def test_name_fuer_mails():
    assert notify.plain_name("Erika  Müller-Lüdenscheid") == "Erika Müller-Lüdenscheid"
    assert notify.plain_name("http://x.example.org/a?b=1") == "httpxexampleorgab"
    assert len(notify.plain_name("A" * 200)) == 40
    assert notify.plain_name(None) == ""


def test_link_hoechstens_bis_zum_tag_nach_dem_termin(c, fest, club):
    """S-05: Ein Scan-Link gilt höchstens bis zum Ende des Tags nach der Veranstaltung."""
    einrichten(c, fest, prices=FREE)
    link = ok(
        c.post(
            f"{fest['url']}scan-links/",
            {"label": "Eingang", "expires_at": soon(400)},
            content_type=JSON,
        )
    )
    with tenant_context(club.pk):
        row = ScanLink.objects.select_related("setup__event").get(pk=link["id"])
        assert row.expires_at == scanning.default_expiry(row.setup)
    # Früher geht weiterhin
    early = ok(
        c.post(
            f"{fest['url']}scan-links/",
            {"label": "Vorverkauf", "expires_at": soon(2)},
            content_type=JSON,
        )
    )
    with tenant_context(club.pk):
        assert ScanLink.objects.get(pk=early["id"]).expires_at < timezone.now() + (
            datetime.timedelta(days=3)
        )


def test_link_erlischt_mit_dem_recht_der_anlegenden_person(c, fest, club, board_a):
    """S-05: Verliert die Person, die den Link angelegt hat, ihre Rolle oder ihr Konto,
    gilt der Link nicht mehr."""
    einrichten(c, fest, prices=FREE)
    link = ok(c.post(f"{fest['url']}scan-links/", {"label": "Eingang"}, content_type=JSON))
    api = f"/api/public/scan/{link['url'].rsplit('/', 1)[-1]}/"
    staff = Client()
    assert staff.get(api).status_code == 200
    # Konto gesperrt
    board_a.is_active = False
    board_a.save(update_fields=["is_active"])
    assert staff.get(api).status_code == 404
    board_a.is_active = True
    board_a.save(update_fields=["is_active"])
    assert staff.get(api).status_code == 200
    # Rolle beendet
    with rls_bypass():
        RoleAssignment.objects.filter(user=board_a, organization=club).update(
            valid_until=timezone.localdate() - datetime.timedelta(days=1)
        )
    assert staff.get(api).status_code == 404
    assert staff.post(api, {"code": "T1:egal"}, content_type=JSON).status_code == 404


def test_verweis_statt_nummer_an_der_karte(c, fest, club):
    """S-04: Auch die gescannte Karte gibt der Seite nur einen Verweis mit, keine Nummer."""
    einrichten(c, fest, prices=FREE)
    _sammelanmeldung(c, fest, "anna")
    link = ok(c.post(f"{fest['url']}scan-links/", {"label": "Eingang"}, content_type=JSON))
    api = f"/api/public/scan/{link['url'].rsplit('/', 1)[-1]}/"
    from registrations import tickets

    with tenant_context(club.pk):
        p = Participant.objects.get(membership=fest["anna"])
        code = tickets.code(p)
    card = ok(Client().post(api, {"code": code}, content_type=JSON))["card"]
    assert isinstance(card["id"], str) and card["id"] != str(p.pk)
    with tenant_context(club.pk):
        row = ScanLink.objects.get(pk=link["id"])
        assert scanning.participant_of_ref(row, card["id"]) == p.pk
        assert scanning.participant_of_ref(row, str(p.pk)) is None
        assert scanning.participant_of_ref(row, p.pk) is None
