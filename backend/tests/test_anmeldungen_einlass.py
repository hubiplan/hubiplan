# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Eintrittskarten mit QR-Code und Einlass vor Ort (konzepte/veranstaltungen-anmeldung-gebuehr.md,
Stufe A6). Alle Daten erfunden."""

import uuid

import pytest
from django.core import mail
from django.utils import timezone

from registrations import tickets

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

FREE = [{"name": "Alle", "steps": [{"amount": "0"}]}]


def _anmelden(fest, who="Bernd"):
    client, url = fest["portals"][who]
    price = ok(client.get(f"{url}registration/"))["offer"]["prices"][0]["id"]
    member = fest[who.lower()]
    data = ok(
        client.post(
            f"{url}registration/",
            {"persons": [{"membership_id": member.pk, "price_id": price}]},
            content_type=JSON,
        )
    )
    return client, url, data["mine"][0]


def test_kostenlos_karten_gleich_mit_der_bestaetigung(c, fest, django_capture_on_commit_callbacks):
    einrichten(c, fest, prices=FREE)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        client, url, reg = _anmelden(fest)
    assert reg["has_tickets"] is True
    sent = [m for m in mail.outbox if "Anmeldebestätigung" in m.subject]
    assert sent and "Eintrittskarten liegen bei" in sent[0].body
    names = [a[0] for a in sent[0].attachments]
    assert any(n.startswith("eintrittskarten-") for n in names)
    # Mitgliederbereich und Verwaltung liefern das PDF
    pdf = client.get(f"{url}registration/{reg['id']}/tickets/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert c.get(f"{fest['url']}{reg['id']}/tickets/").status_code == 200
    # Fremde Anmeldung: nicht
    other, other_url = fest["portals"]["Anna"]
    assert other.get(f"{other_url}registration/{reg['id']}/tickets/").status_code == 404


def test_karten_erst_mit_der_zahlung(c, fest, setup, club, django_capture_on_commit_callbacks):
    einrichten(c, fest)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        _client, _url, reg = _anmelden(fest)
    first = [m for m in mail.outbox if "Anmeldebestätigung" in m.subject][0]
    assert "Eintrittskarten" not in first.body
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
    paid = [m for m in mail.outbox if "Zahlung eingegangen" in m.subject]
    assert paid and any(a[0].startswith("eintrittskarten-") for a in paid[0].attachments)


def test_einlass_mit_code_und_liste(c, fest, club):
    from core.tenancy import tenant_context
    from registrations.models import Participant

    einrichten(c, fest, prices=FREE)
    _client, _url, reg = _anmelden(fest)
    with tenant_context(club.pk):
        person = Participant.objects.get(registration_id=reg["id"])
        code = tickets.code(person)
    assert tickets.participant_of(code) == person.pk
    assert tickets.participant_of(code[:-2] + "xx") is None
    assert tickets.participant_of("T" + str(person.pk)) is None
    url = f"{fest['url']}checkin/"
    listing = ok(c.get(url))
    assert listing["count"] == 1 and listing["checked_in"] == 0
    assert listing["participants"][0]["paid_state"] == "free"
    done = ok(c.post(url, {"code": code}, content_type=JSON))
    assert done["result"] == "ok" and done["participant"]["checked_in_at"]
    again = ok(c.post(url, {"code": code}, content_type=JSON))
    assert again["result"] == "already"
    assert ok(c.post(url, {"code": "irgendwas"}, content_type=JSON))["result"] == "unknown"
    assert ok(c.get(url))["checked_in"] == 1
    board = ok(c.get(fest["url"]))
    assert board["registrations"][0]["participants"][0]["checked_in_at"]
    undo = ok(c.post(url, {"participant": person.pk, "undo": True}, content_type=JSON))
    assert undo["result"] == "undone" and undo["participant"]["checked_in_at"] is None
    assert ok(c.post(url, {"participant": person.pk}, content_type=JSON))["result"] == "ok"
    assert c.post(url, {}, content_type=JSON).status_code == 400
    # Abgemeldet: Karte gilt nicht mehr
    ok(c.post(f"{fest['url']}{reg['id']}/cancel/", {"reason": "krank"}, content_type=JSON))
    assert ok(c.post(url, {"code": code}, content_type=JSON))["result"] == "cancelled"
    assert ok(c.get(url))["count"] == 0
    assert ok(c.get(fest["url"]))["registrations"][0]["has_tickets"] is False


def test_namensschilder_und_bescheinigungen(c, fest, club):
    from core.tenancy import tenant_context
    from registrations import onsite
    from registrations.models import Participant, RegistrationSetup

    einrichten(c, fest, prices=FREE)
    _anmelden(fest)
    _anmelden(fest, "Anna")
    badges = c.get(f"{fest['url']}badges/")
    assert badges.status_code == 200 and badges.content.startswith(b"%PDF")
    certs = c.get(f"{fest['url']}certificates/")
    assert certs.status_code == 200 and certs.content.startswith(b"%PDF")
    with tenant_context(club.pk):
        setup = RegistrationSetup.objects.get(event_id=fest["event"]["id"])
        # Ohne Einlass gelten alle; nach dem ersten Abhaken nur die Eingelassenen
        rows, filtered = onsite.present(setup)
        assert len(rows) == 2 and not filtered
        p = Participant.objects.filter(registration__setup=setup).first()
    ok(c.post(f"{fest['url']}checkin/", {"participant": p.pk}, content_type=JSON))
    with tenant_context(club.pk):
        rows, filtered = onsite.present(setup)
        assert [r.pk for r in rows] == [p.pk] and filtered
    # Mitglieder ohne Bearbeitungsrecht bekommen keine Bescheinigungen
    member, url = fest["portals"]["Anna"]
    assert member.get(f"{fest['url']}certificates/").status_code in (403, 404)


def test_qualifikation_fuer_teilnehmende(c, fest, club):
    from core.tenancy import tenant_context
    from qualifications.models import Qualification, QualificationType

    club.enabled_modules = sorted({*club.enabled_modules, "qualifications"})
    club.save()
    with tenant_context(club.pk):
        kind = QualificationType.objects.create(
            organization=club, name="Standaufsicht", validity_months=24
        )
    einrichten(c, fest, prices=FREE)
    _anmelden(fest)
    board = ok(c.get(fest["url"]))
    assert board["qualification_kinds"] == [{"id": kind.pk, "name": "Standaufsicht"}]
    url = f"{fest['url']}qualification/"
    # Veranstaltung liegt in der Zukunft: Datum fehlt → abgelehnt
    assert c.post(url, {"kind": kind.pk}, content_type=JSON).status_code == 400
    today = timezone.localdate().isoformat()
    first = ok(c.post(url, {"kind": kind.pk, "acquired_on": today}, content_type=JSON))
    assert first["created"] == 1 and first["guests"] == 0
    again = ok(c.post(url, {"kind": kind.pk, "acquired_on": today}, content_type=JSON))
    assert again["created"] == 0 and again["existing"] == 1
    with tenant_context(club.pk):
        q = Qualification.objects.get(kind=kind)
        assert q.person_id == fest["bernd"].person_id and q.valid_until is not None
    assert c.post(url, {"kind": 999999, "acquired_on": today}, content_type=JSON).status_code == 400
