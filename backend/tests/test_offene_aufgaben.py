"""Startseite: offene Aufgaben (Datenänderungen, Wechsel, Fotos, Rückmeldungen)."""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from core.tenancy import tenant_context
from events.models import Event, EventResponse
from members.models import MemberType, TransferRequest
from members.photo_models import MemberPhoto
from portal.models import ChangeRequest

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db


def url(org):
    return f"/api/orgs/{org.pk}/open-tasks/"


@pytest.fixture
def erika(orgs):
    return make_member(orgs["a"], "Erika", "Muster")


def test_sammelt_offene_vorgaenge(api, orgs, board_a, erika):
    a = orgs["a"]
    a.enabled_modules = ["members", "events"]
    a.save()
    with tenant_context(a.pk):
        ChangeRequest.objects.create(organization=a, membership=erika, data={"city": "X"})
        ChangeRequest.objects.create(
            organization=a, membership=erika, data={}, status=ChangeRequest.Status.ACCEPTED
        )
        MemberPhoto.objects.create(
            organization=a,
            membership=erika,
            status=MemberPhoto.Status.PENDING,
            image=ContentFile(b"\xff\xd8bild", name="b.jpg"),
            thumbnail=ContentFile(b"\xff\xd8klein", name="t.jpg"),
        )
        soon = timezone.now() + datetime.timedelta(days=3)
        event = Event.objects.create(
            organization=a,
            title="Sommerfest",
            starts_at=soon,
            ends_at=soon + datetime.timedelta(hours=3),
            rsvp_enabled=True,
        )
        EventResponse.objects.create(
            organization=a, event=event, membership=erika, status="yes", source="member"
        )
        Event.objects.create(
            organization=a,
            title="Später",
            starts_at=soon + datetime.timedelta(days=60),
            ends_at=soon + datetime.timedelta(days=60, hours=1),
            rsvp_enabled=True,
        )
    b_type = MemberType.objects.create(organization=orgs["b"], name="aktiv", active=True)
    TransferRequest.objects.create(
        scope=orgs["federation"],
        person=erika.person,
        from_org=a,
        to_org=orgs["b"],
        member_type=b_type,
        entry_date=datetime.date(2026, 1, 1),
    )

    items = api(board_a).get(url(a)).json()["items"]
    kinds = sorted(i["kind"] for i in items)
    assert kinds == ["change_request", "event", "photo", "transfer"]
    event_item = next(i for i in items if i["kind"] == "event")
    assert "1 Zusagen" in event_item["detail"]
    assert event_item["link"].startswith(f"/termine?termin={event.pk}&datum=")
    photo = next(i for i in items if i["kind"] == "photo")
    assert photo["link"] == f"/mitglieder/{erika.pk}"


def test_nur_mit_passendem_recht(api, orgs, erika):
    a = orgs["a"]
    with tenant_context(a.pk):
        ChangeRequest.objects.create(organization=a, membership=erika, data={"city": "X"})
    reader = make_user("lesen@example.org")
    give_role(reader, a, permissions=["members.view"], name="Lesen")
    assert api(reader).get(url(a)).json()["items"] == []


def test_ueberfaellige_rechnungen_als_ein_eintrag(api, orgs, board_a, erika):
    """UX-Audit 10.6: „Zu erledigen“ nennt überfällige Rechnungen gesammelt."""
    from decimal import Decimal

    from billing.models import Invoice

    a = orgs["a"]
    a.enabled_modules = ["members", "billing"]
    a.save()
    with tenant_context(a.pk):
        for number, due in ((1, datetime.date(2025, 1, 15)), (2, datetime.date(2025, 3, 1))):
            Invoice.objects.create(
                organization=a,
                membership=erika,
                recipient_kind="member",
                recipient_name="Erika Muster",
                date=datetime.date(2025, 1, 1),
                due_date=due,
                year=2025,
                number=number,
                status="open",
                total=Decimal("10.00"),
            )
    items = api(board_a).get(url(a)).json()["items"]
    overdue = [i for i in items if i["kind"] == "invoices_overdue"]
    assert len(overdue) == 1
    assert overdue[0]["title"] == "2 Rechnungen überfällig"
    assert "15.01.2025" in overdue[0]["detail"]
    assert overdue[0]["link"] == "/finanzen/rechnungen?status=open&ueberfaellig=1"


def test_belegung_kontaktformular_und_alte_entwuerfe(api, orgs, board_a):
    """Menüprüfung M-13: auch Belegungsanfragen, zurückgehaltene Nachrichten, alte Entwürfe."""
    from bookings.models import Booking
    from circulars.models import Circular, MailingList
    from materials.models import MaterialItem
    from website.contact_models import HeldMessage
    from website.models import Website

    a = orgs["a"]
    a.enabled_modules = ["members", "website", "infrastructure", "circulars"]
    a.save()
    with tenant_context(a.pk):
        house = MaterialItem.objects.create(
            organization=a,
            kind="facility",
            title="Schützenhaus",
            description="Vereinsheim",
            location_kind="address",
            address={"street": "Musterweg 1", "postal_code": "12345", "city": "Musterstadt"},
            facility_type="building",
            booking_rules={"enabled": True, "approval": True},
        )
        start = timezone.now() + datetime.timedelta(days=5)
        Booking.objects.create(
            organization=a,
            item=house,
            title="Geburtstag",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=3),
        )
        Booking.objects.create(
            organization=a,
            item=house,
            title="Schon bestätigt",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=1),
            status="confirmed",
        )
        site = Website.objects.create(organization=a, public_key="k" * 20, state="public")
        HeldMessage.objects.create(
            organization=a,
            website=site,
            recipient="allgemein",
            recipient_name="Vorstand",
            sender_name="Max Beispiel",
            sender_email="max@example.org",
            subject="Frage",
            body="Hallo",
            reason="Link",
        )
        old = Circular.objects.create(organization=a, subject="Einladung", created_by=board_a)
        fresh = Circular.objects.create(organization=a, subject="Neu", created_by=board_a)
        # Muster eines Verteilers ist auch ein Entwurf, gehört aber nicht zu „Zu erledigen“
        pattern = Circular.objects.create(
            organization=a, subject="Verteiler Alle Mitglieder", created_by=board_a
        )
        MailingList.objects.create(
            organization=a, name="Alle Mitglieder", local_part="alle-a", pattern=pattern
        )
        Circular.objects.filter(pk__in=[old.pk, pattern.pk]).update(
            updated_at=timezone.now() - datetime.timedelta(days=10)
        )

    items = api(board_a).get(url(a)).json()["items"]
    kinds = sorted(i["kind"] for i in items)
    assert kinds == ["booking", "circular_draft", "contact_held"]
    booking = next(i for i in items if i["kind"] == "booking")
    assert booking["title"] == "Schützenhaus"
    assert booking["link"].startswith("/belegung?ab=")
    held = next(i for i in items if i["kind"] == "contact_held")
    assert held["title"] == "1 Nachricht wartet auf Freigabe"
    assert held["link"] == "/webseite/kontakt"
    draft = next(i for i in items if i["kind"] == "circular_draft")
    assert draft["link"] == f"/rundschreiben/{old.pk}"
    assert fresh.pk != old.pk

    reader = make_user("lesen2@example.org")
    give_role(reader, a, permissions=["infrastructure.view"], name="Lesen")
    assert api(reader).get(url(a)).json()["items"] == []
