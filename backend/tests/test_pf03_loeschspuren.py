"""Löschung erfasst auch Antrags-PDF, Empfängerlisten, Rückmeldungen und Untereinheiten.

Gesamtaudit 15.11.: PF-03 (Antrags-PDF blieb dauerhaft, FF-28 (a)), PF-04 (Empfängerlisten
und Verteiler-Eingänge nie gelöscht), PF-17 (Qualifikationen, Protokoll und Rückgängig-Speicher
nur im Verein selbst), PF-18 (Bemerkungen, Helferdienste), PF-19 (Absender des
Kontaktformulars unbefristet). Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest
from django.utils import timezone

from admission.services import store_pdf
from circulars.models import Circular, CircularRecipient, InboundMail
from core.tenancy import rls_bypass, tenant_context
from events.models import Event, EventResponse
from helpers.models import Duty, HelperPlan, Shift, ShiftAssignment
from members.models import Membership
from members.workflows import NAME_PURGED, purge_membership
from outbox.models import EMPTIED, OutgoingMail
from outbox.purge import SUBJECT_EMPTIED, purge_inbound, purge_sent
from qualifications.models import Qualification, QualificationType

from .factories import make_member, make_org
from .test_gesamtaudit_1311 import _angenommen
from .test_mitgliedsantrag import club, leichte_aufgabe  # noqa: F401  (Fixtures)


@pytest.mark.django_db(transaction=True)
def test_antrags_pdf_geht_mit_der_mitgliedschaft(club):
    app, _, _ = _angenommen(club)
    org = club["org"]
    with tenant_context(org.pk):
        store_pdf(app)
        app.refresh_from_db()
        assert app.pdf and app.signature is not None
        name = app.pdf.name
        assert app.pdf.storage.exists(name)
        membership = Membership.objects.get(pk=app.membership_id)
        purge_membership(membership, after_deadline=True)
        app.refresh_from_db()
    assert not app.pdf
    assert not app.pdf.storage.exists(name)
    assert app.mandate == {} and app.guardians == [] and app.signature == {}
    assert set(app.data) <= {"first_name", "last_name"}
    assert app.data_purged_at is not None
    assert app.number  # Nummer und Entscheidung bleiben


@pytest.mark.django_db
def test_empfaenger_rueckmeldungen_helfer_und_untereinheiten():
    club_ = make_org("Verein Spuren")
    unit = make_org("Spielmannszug", "unit", parent=club_)
    member = make_member(club_, "Erika", "Muster")
    start = timezone.now() + datetime.timedelta(days=3)
    with tenant_context(club_.pk):
        circular = Circular.objects.create(
            organization=club_,
            subject="Einladung",
            kind=Circular.Kind.INFO,
            audience=Circular.Audience.MEMBERS,
        )
        recipient = CircularRecipient.objects.create(
            organization=club_,
            club=club_,
            circular=circular,
            membership=member,
            channel="mail",
            first_name="Erika",
            last_name="Muster",
            email="erika.spuren@example.org",
            address="Lindenweg 4, 12345 Musterstadt",
            values={"anrede": "Liebe Erika"},
            status="sent",
        )
        event = Event.objects.create(
            organization=club_, title="Probe", starts_at=start, ends_at=start
        )
        response = EventResponse.objects.create(
            event=event,
            membership=member,
            status="yes",
            source="member",
            note="komme später, Tel. 0123 456",
        )
        plan = HelperPlan.objects.create(organization=club_, title="Fest")
        duty = Duty.objects.create(organization=club_, plan=plan, name="Theke")
        shift = Shift.objects.create(
            organization=club_, duty=duty, starts_at=start, ends_at=start, needed=2
        )
        helper = ShiftAssignment.objects.create(
            organization=club_, shift=shift, membership=member, name="Erika Muster", phone="0123"
        )
    with tenant_context(unit.pk):
        kind = QualificationType.objects.create(organization=unit, name="Übungsleitung")
        Qualification.objects.create(
            organization=unit,
            person=member.person,
            kind=kind,
            acquired_on=datetime.date(2020, 1, 1),
        )

    with tenant_context(club_.pk):
        purge_membership(Membership.objects.get(pk=member.pk), after_deadline=True)
    with rls_bypass():
        recipient.refresh_from_db()
        response.refresh_from_db()
        helper.refresh_from_db()
        assert not Qualification.objects.filter(person=member.person).exists()
    assert (recipient.first_name, recipient.last_name, recipient.email) == ("", "", "")
    assert recipient.address == "" and recipient.values == {}
    assert recipient.status == "sent"  # Zustellstand bleibt
    assert response.note == "" and response.status == "yes"
    assert (helper.name, helper.phone) == (NAME_PURGED, "")


@pytest.mark.django_db
def test_kontaktformular_und_verteiler_eingaenge():
    now = timezone.now()
    with rls_bypass():
        contact = OutgoingMail.objects.create(
            to="vorstand@example.org",
            subject="Webseite: Frage zu meinem Sohn Max",
            body="Nachricht",
            kind="website-contact",
            reply_to="mutter@example.org",
            status=OutgoingMail.Status.SENT,
        )
        normal = OutgoingMail.objects.create(
            to="mitglied@example.org",
            subject="Rechnung 2026-001",
            body="Text",
            kind="rechnung",
            reply_to="kasse@example.org",
            status=OutgoingMail.Status.SENT,
        )
        OutgoingMail.objects.filter(pk__in=[contact.pk, normal.pk]).update(
            created_at=now - datetime.timedelta(days=8)
        )
        old = InboundMail.objects.create(
            sender="fremd@example.org", subject="Alt", status=InboundMail.Status.REJECTED
        )
        InboundMail.objects.filter(pk=old.pk).update(received_at=now - datetime.timedelta(days=91))
        fresh = InboundMail.objects.create(
            sender="neu@example.org", subject="Neu", status=InboundMail.Status.REJECTED
        )
    purge_sent(now)
    assert purge_inbound(now) == 1
    with rls_bypass():
        contact.refresh_from_db()
        normal.refresh_from_db()
        assert set(InboundMail.objects.values_list("pk", flat=True)) >= {fresh.pk}
        assert not InboundMail.objects.filter(pk=old.pk).exists()
    assert contact.body == EMPTIED
    assert contact.reply_to == "" and contact.subject == SUBJECT_EMPTIED
    # Andere Mails erst nach 30 Tagen, und Betreff und Antwort-an bleiben als Nachweis
    assert normal.body == "Text" and normal.reply_to == "kasse@example.org"
