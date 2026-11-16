"""Erziehungsberechtigte (Konzept Familien, Haushalte und Firmen, H4).

Erziehungsberechtigte sind Ansprechpartner (``ContactPerson``) einer minderjährigen
Person mit ``is_guardian``. Mit „Mitgliederzugang“ bekommen sie einen eigenen Zugang zum
Kind (``PortalAccess`` je Ansprechpartner, wie bei Organisationen, J5).

Am 18. Geburtstag endet das: Zugang und Eintrag werden gelöscht (Kontaktdaten der Eltern
bleiben nur, wenn sie selbst Mitglied sind, dann in ihrer eigenen Akte). Vier Wochen
vorher bekommen die Erziehungsberechtigten eine Mail (Fachfrage FH-9).
"""

from __future__ import annotations

import datetime
import logging

from dateutil.relativedelta import relativedelta
from django.db import transaction

from .models import ContactPerson, Membership, today

logger = logging.getLogger(__name__)

ADULT_AGE = 18
NOTICE_DAYS = 28


def age_on(birth: datetime.date, on: datetime.date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def is_minor(person, on: datetime.date | None = None) -> bool:
    """Minderjährig: Person mit Geburtsdatum unter 18. Ohne Geburtsdatum nicht."""
    if person.is_organization or person.birth_date is None:
        return False
    return age_on(person.birth_date, on or today()) < ADULT_AGE


# Einwilligung eines Kindes in die Verarbeitung (Art. 8 DSGVO): unter 16 durch die
# Erziehungsberechtigten (Gesamtaudit 15.11., PF-21)
CONSENT_AGE = 16


def needs_guardian_consent(person, on: datetime.date | None = None) -> bool:
    """Unter 16 (nach Geburtsdatum; nur Jahrgang: so jung wie möglich gerechnet)."""
    if person.is_organization or person.birth_date is None:
        return False
    birth = person.birth_date
    if getattr(person, "birth_year_only", False):
        birth = birth.replace(month=12, day=31)
    return age_on(birth, on or today()) < CONSENT_AGE


def adult_on(person) -> datetime.date | None:
    """Tag der Volljährigkeit. Ist nur das Geburtsjahr bekannt, spätestmöglich (31.12.):
    Die Erziehungsberechtigung endet so nie vor dem 18. Geburtstag (Gesamtaudit 15.11., PF-27)."""
    if person.birth_date is None:
        return None
    birth = person.birth_date
    if getattr(person, "birth_year_only", False):
        birth = birth.replace(month=12, day=31)
    return birth + relativedelta(years=ADULT_AGE)


def guardians_of(membership: Membership):
    return ContactPerson.objects.filter(membership=membership, is_guardian=True).select_related(
        "person"
    )


@transaction.atomic
def end_for(membership: Membership, user=None) -> int:
    """Erziehungsberechtigung einer volljährigen Person beenden: Zugänge der Eltern und
    ihre Einträge löschen."""
    from audit.log import diff, record, snapshot
    from portal.models import PortalAccess

    count = 0
    for contact in guardians_of(membership):
        PortalAccess.objects.filter(contact_person=contact).delete()
        record(
            membership.organization,
            user,
            "delete",
            contact,
            {**diff(snapshot(contact), {}), "Grund": [None, "volljährig"]},
            person=membership.person,
        )
        contact.delete()
        count += 1
    return count


def end_adults(on: datetime.date | None = None) -> int:
    """Täglich: Erziehungsberechtigte aller Volljährigen beenden."""
    from core.tenancy import tenant_context

    on = on or today()
    count = 0
    for membership in _guardian_memberships():
        person = membership.person
        adult = adult_on(person)
        if adult is None or person.is_organization or on < adult:
            continue
        with tenant_context(membership.organization_id):
            count += end_for(membership)
    return count


def _guardian_memberships():
    """Mitgliedschaften mit Erziehungsberechtigten. Das Geburtsdatum ist verschlüsselt und
    lässt sich nicht in der Datenbank vergleichen; geprüft wird deshalb hier."""
    from core.tenancy import rls_bypass, tenant_context

    with rls_bypass():
        ids = list(
            ContactPerson.objects.filter(is_guardian=True)
            .values_list("membership_id", "organization_id")
            .distinct()
        )
    for membership_id, org_id in ids:
        with tenant_context(org_id):
            membership = (
                Membership.objects.select_related("person", "organization")
                .filter(pk=membership_id)
                .first()
            )
        if membership is not None:
            yield membership


def notice_text(membership: Membership) -> tuple[str, str]:
    """Betreff und Text der Mail vier Wochen vor dem 18. Geburtstag (Vereinssprache)."""
    from django.utils.translation import gettext

    from core.i18n import date_text

    person = membership.person
    org = membership.organization
    subject = gettext("{name}: Elternzugang endet mit dem 18. Geburtstag").format(name=org.name)
    body = gettext(
        "Guten Tag,\n\n"
        "{first_name} {last_name} wird am {day} volljährig. Ab dann endet bei {club} Ihr "
        "Zugang als Erziehungsberechtigte bzw. Erziehungsberechtigter, und Ihre "
        "Kontaktangaben werden beim Mitglied gelöscht. Einwilligungen, die Sie gegeben "
        "haben, gelten weiter, bis das Mitglied sie widerruft.\n\n"
        "Das Mitglied kann danach einen eigenen Zugang bekommen.\n\n"
        "Viele Grüße\n{club}\n"
    ).format(
        first_name=person.first_name,
        last_name=person.last_name,
        day=date_text(adult_on(person)),
        club=org.name,
    )
    return subject, body


def send_notices(on: datetime.date | None = None) -> int:
    """Täglich: Mail an Erziehungsberechtigte, deren Kind in vier Wochen 18 wird."""
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError

    from core.i18n import language_of_org
    from core.tenancy import tenant_context
    from outbox import mail
    from portal.services import contact_email

    on = on or today()
    sent = 0
    for membership in _guardian_memberships():
        # Ab vier Wochen vorher bis zum Tag der Volljährigkeit, einmal je Erziehungsberechtigtem:
        # Vorher nur am genauen Tag; fiel der Lauf aus oder lag der Geburtstag auf dem 29.02.,
        # kam nie ein Hinweis (Gesamtaudit 15.11., PF-27)
        adult = adult_on(membership.person)
        if adult is None or membership.person.is_organization:
            continue
        if not adult - datetime.timedelta(days=NOTICE_DAYS) <= on < adult:
            continue
        with tenant_context(membership.organization_id):
            org = membership.organization
            with language_of_org(org):
                subject, body = notice_text(membership)
            for contact in guardians_of(membership).filter(adult_notice_at__isnull=True):
                # Erst vermerken, dann senden: lieber ein Hinweis zu wenig als doppelt
                claimed = ContactPerson.objects.filter(
                    pk=contact.pk, adult_notice_at__isnull=True
                ).update(adult_notice_at=timezone.now())
                if not claimed:
                    continue
                try:
                    address = contact_email(org, contact)
                except ValidationError:
                    logger.info("Erziehungsberechtigter %s ohne E-Mail-Adresse", contact.pk)
                    continue
                if mail.send(
                    address,
                    subject,
                    body,
                    organization=org,
                    kind="guardian_notice",
                    fail_silently=True,
                ):
                    sent += 1
    return sent
