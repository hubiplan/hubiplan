"""Anmeldungen: Preise, freie Plätze, anmelden, abmelden, Rechnung, Zahlungseingang.

Konzept konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufen A1 und A2.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from members.models import Membership, today

from .models import Participant, PriceOption, PriceStep, Registration, RegistrationSetup

ZERO = Decimal("0.00")
MODULE = "registrations"


def module_on(org) -> bool:
    return MODULE in (org.enabled_modules or [])


def setup_of(event) -> RegistrationSetup | None:
    try:
        return event.registration_setup
    except RegistrationSetup.DoesNotExist:
        return None


def first_day(setup: RegistrationSetup) -> datetime.date:
    return timezone.localtime(setup.event.starts_at).date()


def age_on(birth: datetime.date, on: datetime.date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


# --- Plätze und Preise ---


def _active(qs):
    return qs.filter(
        status=Participant.Status.ACTIVE, registration__status=Registration.Status.REGISTERED
    )


def taken(setup: RegistrationSetup) -> int:
    return _active(Participant.objects.filter(registration__setup=setup)).count()


def taken_for_price(price: PriceOption) -> int:
    return _active(Participant.objects.filter(price=price)).count()


def taken_for_step(step: PriceStep) -> int:
    return _active(Participant.objects.filter(step=step)).count()


def free(setup: RegistrationSetup) -> int | None:
    if setup.capacity is None:
        return None
    return max(0, setup.capacity - taken(setup))


def current_step(
    price: PriceOption, on: datetime.date, extra: dict[int, int] | None = None
) -> PriceStep | None:
    """Die Preisstufe, die heute gilt; ``extra``: in dieser Anmeldung schon vergeben."""
    extra = extra or {}
    for step in price.steps.all():
        if step.until_date is not None and on > step.until_date:
            continue
        if (
            step.until_count is not None
            and taken_for_step(step) + extra.get(step.pk, 0) >= step.until_count
        ):
            continue
        return step
    return None


def state(setup: RegistrationSetup, now: datetime.datetime | None = None) -> str:
    """not_yet | open | closed | full | cancelled"""
    now = now or timezone.now()
    if setup.event.is_cancelled:
        return "cancelled"
    if not setup.is_open or now > setup.closes_at:
        return "closed"
    if setup.opens_at and now < setup.opens_at:
        return "not_yet"
    if setup.capacity is not None and taken(setup) >= setup.capacity:
        return "full"
    return "open"


STATE_LABELS = {
    "not_yet": "Die Anmeldung beginnt am {when}.",
    "open": "Anmeldung möglich bis {when}.",
    "closed": "Die Anmeldung ist geschlossen.",
    "full": "Leider sind alle Plätze vergeben.",
    "cancelled": "Der Termin ist abgesagt.",
}


def state_text(setup: RegistrationSetup, value: str) -> str:
    from core.i18n import datetime_text

    when = setup.opens_at if value == "not_yet" else setup.closes_at
    return gettext(STATE_LABELS[value]).format(when=datetime_text(when) if when else "")


def price_label(price: PriceOption, lang: str = "de") -> str:
    return (price.name_en if lang == "en" and price.name_en else price.name).strip()


def step_data(step: PriceStep) -> dict:
    return {
        "id": step.pk,
        "name": step.name,
        "amount": str(step.amount),
        "until_date": step.until_date,
        "until_count": step.until_count,
        "taken": taken_for_step(step),
    }


def price_data(price: PriceOption, on: datetime.date, *, full: bool = False) -> dict:
    step = current_step(price, on)
    steps = list(price.steps.all())
    nxt = None
    if step is not None and step in steps:
        index = steps.index(step)
        nxt = steps[index + 1] if index + 1 < len(steps) else None
    remaining = None
    if step is not None and step.until_count is not None:
        remaining = max(0, step.until_count - taken_for_step(step))
    data = {
        "id": price.pk,
        "name": price.name,
        "name_en": price.name_en,
        "applies": price.applies,
        "age_from": price.age_from,
        "age_to": price.age_to,
        "capacity": price.capacity,
        "free": (
            max(0, price.capacity - taken_for_price(price)) if price.capacity is not None else None
        ),
        "vat_rate": str(price.vat_rate) if price.vat_rate is not None else None,
        "is_active": price.is_active,
        "current": (
            {
                "id": step.pk,
                "name": step.name,
                "amount": str(step.amount),
                "until_date": step.until_date,
                "remaining": remaining,
            }
            if step
            else None
        ),
        "next": (
            {"name": nxt.name, "amount": str(nxt.amount), "until_date": nxt.until_date}
            if nxt
            else None
        ),
    }
    if full:
        data["steps"] = [step_data(s) for s in steps]
        data["taken"] = taken_for_price(price)
    return data


def offer_data(setup: RegistrationSetup, *, full: bool = False) -> dict:
    on = timezone.localdate()
    value = state(setup)
    prices = setup.prices.prefetch_related("steps")
    if not full:
        prices = prices.filter(is_active=True)
    return {
        "id": setup.pk,
        "state": value,
        "state_text": state_text(setup, value),
        "opens_at": setup.opens_at,
        "closes_at": setup.closes_at,
        "is_open": setup.is_open,
        "capacity": setup.capacity,
        "free": free(setup),
        "taken": taken(setup),
        "max_persons": setup.max_persons,
        "guests_allowed": setup.guests_allowed,
        "due_days": setup.due_days,
        "category": setup.category_id,
        "terms": setup.terms,
        "prices": [price_data(p, on, full=full) for p in prices],
    }


# --- Wer gehört zur Familie ---


def family_of(membership: Membership) -> list[Membership]:
    """Aktuelle Mitglieder der Familienhaushalte des Mitglieds (ohne es selbst)."""
    from members.households import current_links
    from members.models import Household

    homes = list(
        current_links([membership.pk], kind=Household.Kind.FAMILY).values_list(
            "household_id", flat=True
        )
    )
    if not homes:
        return []
    from members.models import HouseholdMember

    on = today()
    ids = (
        HouseholdMember.objects.filter(household_id__in=homes, valid_from__lte=on)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
        .exclude(membership_id=membership.pk)
        .values_list("membership_id", flat=True)
    )
    return list(
        Membership.objects.filter(pk__in=list(ids), purged_at__isnull=True)
        .select_related("person")
        .order_by("pk")
    )


def registered_memberships(setup: RegistrationSetup) -> set[int]:
    return set(
        _active(
            Participant.objects.filter(registration__setup=setup, membership__isnull=False)
        ).values_list("membership_id", flat=True)
    )


# --- Anmelden ---


@dataclass
class PersonInput:
    membership: Membership | None
    name: str
    birth_date: datetime.date | None
    price: PriceOption


def _lock_setup(setup: RegistrationSetup) -> None:
    RegistrationSetup.objects.select_for_update().filter(pk=setup.pk).values_list("pk").first()


def next_number(org_id: int, year: int) -> int:
    with connection.cursor() as cursor:
        # eigener Sperrschlüssel, getrennt von Rechnungs- und Buchungsnummern
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [org_id, 300000 + year])
    last = (
        Registration.objects.filter(organization_id=org_id, year=year)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    return (last or 0) + 1


def _check_person(setup, person: PersonInput, start: datetime.date, board: bool) -> None:
    price = person.price
    if price.setup_id != setup.pk or (not price.is_active and not board):
        raise ValidationError(gettext("Bitte einen gültigen Tarif wählen."))
    if price.applies == PriceOption.Applies.MEMBERS and person.membership is None:
        raise ValidationError(
            gettext("Den Tarif „{price}“ gibt es nur für Mitglieder.").format(price=price.name)
        )
    if price.applies == PriceOption.Applies.GUESTS and person.membership is not None:
        raise ValidationError(
            gettext("Den Tarif „{price}“ gibt es nur für Gäste.").format(price=price.name)
        )
    if price.age_from is None and price.age_to is None:
        return
    birth = person.birth_date
    if birth is None and person.membership is not None:
        birth = person.membership.person.birth_date
    if birth is None:
        if board:
            return
        raise ValidationError(
            gettext("Für den Tarif „{price}“ brauchen wir das Geburtsdatum von {name}.").format(
                price=price.name, name=person.name
            )
        )
    age = age_on(birth, start)
    if (price.age_from is not None and age < price.age_from) or (
        price.age_to is not None and age > price.age_to
    ):
        raise ValidationError(
            gettext("{name} passt nicht in den Tarif „{price}“ (Alter {age}).").format(
                name=person.name, price=price.name, age=age
            )
        )


@transaction.atomic
def register(
    setup: RegistrationSetup,
    persons: list[PersonInput],
    *,
    booker: Membership | None,
    name: str,
    email: str,
    phone: str = "",
    address: str = "",
    note: str = "",
    source: str,
    user=None,
    terms_accepted: bool = False,
) -> Registration:
    """Verbindlich anmelden. Prüft Plätze unter Sperre, hält die Preise fest, stellt die
    Rechnung aus und schickt die Anmeldebestätigung (nach dem Speichern)."""
    _lock_setup(setup)
    setup.refresh_from_db()
    board = source == Registration.Source.BOARD
    value = state(setup)
    if value == "cancelled":
        raise ValidationError(gettext("Der Termin ist abgesagt."))
    if not board and value != "open":
        raise ValidationError(state_text(setup, value))
    if not persons:
        raise ValidationError(gettext("Bitte mindestens eine Person anmelden."))
    if len(persons) > setup.max_persons:
        raise ValidationError(
            gettext("Höchstens {n} Personen je Anmeldung.").format(n=setup.max_persons)
        )
    if setup.terms and not board and not terms_accepted:
        raise ValidationError(gettext("Bitte die Teilnahmebedingungen bestätigen."))
    if not name.strip():
        raise ValidationError(gettext("Bitte den Namen angeben."))
    start = first_day(setup)
    already = registered_memberships(setup)
    seen: set[int] = set()
    for person in persons:
        if not person.name.strip():
            raise ValidationError(gettext("Bitte für jede Person den Namen angeben."))
        if person.membership is not None:
            if person.membership.pk in already or person.membership.pk in seen:
                raise ValidationError(
                    gettext("{name} ist schon angemeldet.").format(name=person.name)
                )
            seen.add(person.membership.pk)
        elif not setup.guests_allowed and not board:
            raise ValidationError(gettext("Zu diesem Termin können keine Gäste angemeldet werden."))
        _check_person(setup, person, start, board)
    if setup.capacity is not None and taken(setup) + len(persons) > setup.capacity:
        left = max(0, setup.capacity - taken(setup))
        raise ValidationError(
            gettext("Leider sind alle Plätze vergeben.")
            if left == 0
            else gettext("Es sind nur noch {n} Plätze frei.").format(n=left)
        )
    by_price: dict[int, int] = {}
    for person in persons:
        by_price[person.price.pk] = by_price.get(person.price.pk, 0) + 1
    for person in persons:
        price = person.price
        if price.capacity is not None and taken_for_price(price) + by_price[price.pk] > (
            price.capacity
        ):
            raise ValidationError(
                gettext("Im Tarif „{price}“ sind nicht mehr genug Plätze frei.").format(
                    price=price.name
                )
            )
    now = timezone.now()
    org = setup.organization
    year = timezone.localdate().year
    reg = Registration.objects.create(
        setup=setup,
        year=year,
        number=next_number(org.pk, year),
        membership=booker,
        name=name.strip()[:200],
        email=email.strip()[:254],
        phone=phone.strip()[:50],
        address=address.strip()[:1000],
        note=note.strip()[:500],
        language=_language(org),
        source=source,
        terms_accepted_at=now if terms_accepted else None,
        created_by=user,
    )
    on = timezone.localdate()
    extra: dict[int, int] = {}
    total = ZERO
    for index, person in enumerate(persons):
        price = person.price
        step = current_step(price, on, extra)
        if step is None:
            raise ValidationError(
                gettext("Der Tarif „{price}“ ist nicht mehr buchbar.").format(price=price.name)
            )
        extra[step.pk] = extra.get(step.pk, 0) + 1
        label = price.name if not step.name else f"{price.name} – {step.name}"
        Participant.objects.create(
            registration=reg,
            membership=person.membership,
            name=person.name.strip()[:200],
            birth_date=person.birth_date,
            price=price,
            step=step,
            price_name=label[:170],
            amount=step.amount,
            position=index,
        )
        total += step.amount
    reg.total = total
    reg.save(update_fields=["total", "updated_at"])
    if total > 0:
        reg.invoice = create_invoice(reg, user)
        reg.save(update_fields=["invoice", "updated_at"])
    from . import notify

    pk = reg.pk
    transaction.on_commit(lambda: notify.confirmation(pk))
    return reg


def _language(org) -> str:
    from core.i18n import org_language

    return org_language(org)


def payment_category(setup: RegistrationSetup):
    from billing.services import settings_for

    return setup.category or settings_for(setup.organization).category


def due_date(setup: RegistrationSetup, on: datetime.date) -> datetime.date:
    due = on + datetime.timedelta(days=setup.due_days)
    last = first_day(setup) - datetime.timedelta(days=1)
    return max(on, min(due, last))


def create_invoice(reg: Registration, user=None):
    """Rechnung über die Teilnahmegebühr, gleich festgeschrieben."""
    from billing import services as billing
    from billing.models import Invoice, InvoiceLine

    setup = reg.setup
    event = setup.event
    org = reg.organization
    on = timezone.localdate()
    if reg.membership_id is not None:
        kind = Invoice.Recipient.MEMBER
        recipient = billing.member_recipient(org, reg.membership)
    else:
        kind = Invoice.Recipient.REGISTRATION
        recipient = {
            "recipient_name": reg.name,
            "recipient_address": reg.address,
            "recipient_email": reg.email,
        }
    invoice = Invoice.objects.create(
        organization=org,
        recipient_kind=kind,
        membership=reg.membership if kind == Invoice.Recipient.MEMBER else None,
        project=event.project,
        payment_category=setup.category,
        date=on,
        due_date=due_date(setup, on),
        subject=gettext("Teilnahmegebühr {title}").format(title=event.title)[:200],
        note=gettext("Anmeldung {number}. Bitte bei der Überweisung die Rechnungsnummer angeben.")
        .format(number=reg.display_number)
        .strip(),
        created_by=user,
        **recipient,
    )
    for index, p in enumerate(reg.participants.select_related("price")):
        if p.amount <= 0:
            continue
        InvoiceLine.objects.create(
            organization=org,
            invoice=invoice,
            position=index,
            text=f"{event.title}: {p.price_name}"[:200],
            detail=p.name[:200],
            amount=p.amount,
            vat_rate=p.price.vat_rate or None,
        )
    billing.finalize(invoice)
    return invoice


# --- Abmelden ---


def member_can_cancel(setup: RegistrationSetup) -> bool:
    """Mitglieder melden sich selbst bis zum Anmeldeschluss ab (Stufe A1)."""
    return not setup.event.is_cancelled and timezone.now() <= setup.closes_at


@transaction.atomic
def cancel(reg: Registration, *, user=None, reason: str = "", by_member: bool = False):
    Registration.objects.select_for_update().filter(pk=reg.pk).values_list("pk").first()
    reg.refresh_from_db()
    if reg.status == Registration.Status.CANCELLED:
        raise ValidationError(gettext("Die Anmeldung ist schon abgemeldet."))
    if by_member and not member_can_cancel(reg.setup):
        raise ValidationError(
            gettext(
                "Abmelden ist nur bis zum Anmeldeschluss möglich. Bitte wende dich an den Verein."
            )
        )
    reg.status = Registration.Status.CANCELLED
    reg.cancelled_at = timezone.now()
    reg.cancel_reason = reason.strip()[:300]
    reg.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
    reg.participants.update(status=Participant.Status.CANCELLED)
    invoice = reg.invoice
    if invoice is not None and invoice.status in ("open", "paid"):
        from billing import services as billing

        billing.cancel(
            invoice,
            reason or gettext("Abmeldung {number}").format(number=reg.display_number),
            user,
        )
    from . import notify

    pk = reg.pk
    transaction.on_commit(lambda: notify.cancellation(pk))
    return reg


# --- Zahlung ---


def on_invoice_paid(invoice) -> None:
    """Aus billing: Rechnung ist ganz bezahlt. Bestätigung einmal je Anmeldung."""
    rows = list(
        Registration.objects.filter(
            invoice=invoice,
            status=Registration.Status.REGISTERED,
            payment_confirmed_at__isnull=True,
        ).values_list("pk", flat=True)
    )
    if not rows:
        return
    Registration.objects.filter(pk__in=rows).update(payment_confirmed_at=timezone.now())
    from . import notify

    for pk in rows:
        transaction.on_commit(lambda pk=pk: notify.payment_received(pk))


def paid_state(reg: Registration) -> str:
    """free | open | partly | paid | cancelled"""
    if reg.status == Registration.Status.CANCELLED:
        return "cancelled"
    inv = reg.invoice
    if inv is None:
        return "free"
    if inv.status in ("paid", "settled"):
        return "paid"
    if inv.paid > 0:
        return "partly"
    return "open"


def summary(setup: RegistrationSetup) -> dict:
    regs = Registration.objects.filter(setup=setup, status=Registration.Status.REGISTERED)
    totals = regs.aggregate(total=Sum("total"))
    paid = regs.filter(invoice__isnull=False).aggregate(s=Sum("invoice__paid"))["s"] or ZERO
    return {
        "registrations": regs.count(),
        "persons": taken(setup),
        "total": str(totals["total"] or ZERO),
        "paid": str(paid),
        "open": str(max(ZERO, (totals["total"] or ZERO) - paid)),
    }


# --- Datenschutz ---


def forget_membership(membership: Membership) -> None:
    """Daten eines Mitglieds gelöscht: Anmeldungen bleiben gezählt, ohne Person."""
    Registration.objects.filter(membership=membership).update(membership=None)
    Participant.objects.filter(membership=membership).update(membership=None)


GUEST_KEEP_DAYS = 183


def purge_due(now: datetime.datetime | None = None) -> int:
    """Angaben von Anmeldungen ohne Mitgliedschaft ein halbes Jahr nach dem Termin
    anonymisieren (Fachfrage F12). Die Rechnung bleibt nach ihrer eigenen Frist."""
    from core.tenancy import rls_bypass

    now = now or timezone.now()
    limit = now - datetime.timedelta(days=GUEST_KEEP_DAYS)
    done = 0
    with rls_bypass():
        rows = Registration.objects.filter(
            purged_at__isnull=True, setup__event__ends_at__lt=limit
        ).select_related("setup__event")
        for reg in rows.iterator():
            with transaction.atomic():
                parts = reg.participants.filter(membership__isnull=True)
                for p in parts:
                    p.name = gettext("Gast")
                    p.birth_date = None
                    p.save(update_fields=["name", "birth_date"])
                fields = ["purged_at", "updated_at"]
                if reg.membership_id is None:
                    reg.name = gettext("gelöscht")
                    reg.email = ""
                    reg.phone = ""
                    reg.address = ""
                    fields += ["name", "email", "phone", "address"]
                reg.note = ""
                reg.purged_at = now
                reg.save(update_fields=fields + ["note"])
                done += 1
    return done
