"""Kacheln für Mitglieder (Mitgliederbereich und Apps) mit ihrem Anlass."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, ngettext

from access.modules import module_on

from .base import Content, Figure, Row, Tile, count, day_text, euro, hours, today, when_text

ZERO = Decimal("0.00")
# Anlässe (docs/startseite-kacheln.md)
WORKHOURS_LAST_DAYS = 92
REGISTRATION_DAYS = 7
ROWS = 4


@dataclass
class PortalContext:
    access: object
    user: object

    @property
    def org(self):
        return self.access.organization

    @property
    def member(self) -> int:
        return self.access.membership_id

    @property
    def current(self) -> bool:
        return self.access.membership.current_period() is not None


def _event_link(event) -> str:
    day = timezone.localtime(event.starts_at).date()
    return f"/termine?termin={event.pk}&datum={day:%Y-%m-%d}"


# --- 1 Meine Arbeitsstunden ------------------------------------------------------------------


def _my_balance(ctx: PortalContext):
    from billing import workhours

    if not workhours.active(ctx.org):
        return None
    year = ctx.org.fiscal_year_of(today())
    return workhours.balances(ctx.org, year, ids=[ctx.member]).get(ctx.member)


def _workhours_available(ctx: PortalContext) -> bool:
    return ctx.current and _my_balance(ctx) is not None


def _workhours(ctx: PortalContext) -> Content:
    b = _my_balance(ctx)
    org, day = ctx.org, today()
    year = org.fiscal_year_of(day)
    _start, end = org.fiscal_range(year)
    c = Content(
        figures=[
            Figure(gettext("Geleistet"), hours(b.done), "good" if b.missing <= 0 else None),
            Figure(gettext("Soll"), hours(b.required)),
            Figure(gettext("Noch offen"), hours(b.missing), "warn" if b.missing > 0 else "good"),
        ],
        link="/mein-bereich/helferdienste",
        link_label=gettext("Zu den Helferdiensten"),
    )
    if b.missing > 0:
        c.text = gettext(
            "Fehlen am {date} noch Stunden, kostet jede {amount}, zurzeit zusammen {total}."
        ).format(date=day_text(end), amount=euro(b.rate), total=euro(b.amount))
        if (end - day).days < WORKHOURS_LAST_DAYS:
            c.reason = gettext("Bis {date} fehlen dir noch {hours}.").format(
                date=day_text(end), hours=hours(b.missing)
            )
    else:
        c.text = gettext("Dein Soll für {year} ist erfüllt.").format(year=org.fiscal_label(year))
    return c


# --- 2 Offene Umfragen -----------------------------------------------------------------------


def _surveys_available(ctx: PortalContext) -> bool:
    return ctx.current and module_on(ctx.org, "surveys")


def _surveys(ctx: PortalContext) -> Content:
    from surveys import services
    from surveys.models import Survey

    now = timezone.now()
    qs = (
        Survey.objects.filter(organization=ctx.org, status=Survey.Status.OPEN)
        .filter(Q(closes_at__isnull=True) | Q(closes_at__gt=now))
        .order_by("closes_at", "pk")
    )
    answered = services.answered_ids(ctx.member, [s.pk for s in qs])
    waiting = [s for s in qs if s.pk not in answered and services.is_eligible(s, ctx.member)]
    c = Content(link="/mein-bereich/umfragen", link_label=gettext("Zu den Umfragen"))
    for s in waiting[:ROWS]:
        detail = (
            gettext("bis {when}").format(when=when_text(s.closes_at))
            if s.closes_at
            else gettext("ohne Enddatum")
        )
        c.rows.append(Row(s.title, detail, "/mein-bereich/umfragen", "warn"))
    if waiting:
        c.reason = ngettext(
            "Eine Umfrage wartet auf deine Antwort.",
            "{n} Umfragen warten auf deine Antwort.",
            len(waiting),
        ).format(n=count(len(waiting)))
    else:
        c.text = gettext("Keine offene Umfrage für dich.")
    return c


# --- 3 Pinnwand neu --------------------------------------------------------------------------


def _pinboard_available(ctx: PortalContext) -> bool:
    return ctx.current and module_on(ctx.org, "pinboard")


def _pinboard(ctx: PortalContext) -> Content:
    from pinboard import services

    new = services.new_count(ctx.org, ctx.member)
    latest = list(services.visible_for(ctx.org, ctx.member).order_by("-pinned", "-created_at")[:3])
    c = Content(
        figures=[Figure(gettext("Neue Beiträge"), count(new), "warn" if new else None)],
        link="/mein-bereich/pinnwand",
        link_label=gettext("Zur Pinnwand"),
    )
    for n in latest:
        first = (n.text or "").strip().splitlines()[0] if (n.text or "").strip() else ""
        title = first if len(first) <= 80 else first[:79] + "…"
        detail = day_text(timezone.localtime(n.created_at).date())
        if n.author:
            detail = f"{n.author} · {detail}"
        c.rows.append(Row(title, detail, "/mein-bereich/pinnwand"))
    if not latest:
        c.text = gettext("Auf der Pinnwand steht gerade nichts.")
    if new:
        c.reason = ngettext(
            "Ein neuer Beitrag auf der Pinnwand.", "{n} neue Beiträge auf der Pinnwand.", new
        ).format(n=count(new))
    return c


# --- 4 Meine Anmeldungen ---------------------------------------------------------------------


def _registrations_available(ctx: PortalContext) -> bool:
    from registrations.services import module_on as reg_on

    return ctx.current and reg_on(ctx.org)


def _registrations(ctx: PortalContext) -> Content:
    from registrations.models import Registration
    from registrations.views import models_q_member

    now = timezone.now()
    regs = list(
        Registration.objects.filter(models_q_member(ctx.member))
        .filter(
            status__in=[Registration.Status.REGISTERED, Registration.Status.WAITING],
            setup__event__starts_at__gte=now,
        )
        .exclude(setup__event__is_cancelled=True)
        .distinct()
        .select_related("setup__event", "invoice")
        .order_by("setup__event__starts_at", "pk")[:ROWS]
    )
    c = Content(link="/termine", link_label=gettext("Zum Kalender"))
    soon = now + datetime.timedelta(days=REGISTRATION_DAYS)
    for r in regs:
        event = r.setup.event
        parts = [when_text(event.starts_at)]
        tone = None
        if r.status == Registration.Status.WAITING:
            parts.append(gettext("Warteliste"))
        elif r.invoice_id and r.invoice and r.invoice.status == "open":
            parts.append(gettext("noch nicht bezahlt"))
            tone = "warn"
        else:
            parts.append(gettext("angemeldet"))
        c.rows.append(Row(event.title, " · ".join(parts), _event_link(event), tone))
        if event.starts_at <= soon and r.status == Registration.Status.REGISTERED and not c.reason:
            c.reason = gettext(
                "„{title}“ ist bald, die Eintrittskarte findest du am Termin."
            ).format(title=event.title)
    if not regs:
        c.text = gettext("Du bist zurzeit für nichts angemeldet.")
    return c


# --- 5 Sammelbestellung ----------------------------------------------------------------------


def _orders_available(ctx: PortalContext) -> bool:
    return ctx.current and module_on(ctx.org, "orders")


def _orders(ctx: PortalContext) -> Content:
    from orders import services

    day = today()
    running = list(
        services.visible_for(ctx.org, ctx.member)
        .filter(closed_at__isnull=True, deadline__gte=day)
        .order_by("deadline", "pk")[:ROWS]
    )
    ordered = set(
        services.MemberOrder.objects.filter(
            campaign__in=running, membership_id=ctx.member
        ).values_list("campaign_id", flat=True)
    )
    c = Content(link="/mein-bereich/bestellungen", link_label=gettext("Zu den Bestellungen"))
    missing = 0
    for o in running:
        done = o.pk in ordered
        if not done and not services.may_order(o, ctx.member):
            continue
        state = gettext("bestellt") if done else gettext("noch nicht bestellt")
        detail = gettext("bis {date}").format(date=day_text(o.deadline)) + " · " + state
        c.rows.append(Row(o.title, detail, "/mein-bereich/bestellungen", None if done else "warn"))
        missing += 0 if done else 1
    if missing:
        c.reason = ngettext(
            "Eine Sammelbestellung läuft, du hast noch nicht bestellt.",
            "{n} Sammelbestellungen laufen, du hast noch nicht bestellt.",
            missing,
        ).format(n=count(missing))
    if not c.rows:
        c.text = gettext("Zurzeit läuft keine Sammelbestellung.")
    return c


TILES: list[Tile] = [
    Tile(
        "meine-arbeitsstunden",
        lambda: gettext("Meine Arbeitsstunden"),
        lambda: gettext("Geleistet, Soll und was noch offen ist"),
        _workhours_available,
        _workhours,
    ),
    Tile(
        "umfragen",
        lambda: gettext("Offene Umfragen"),
        lambda: gettext("Umfragen, die noch auf deine Antwort warten"),
        _surveys_available,
        _surveys,
    ),
    Tile(
        "pinnwand",
        lambda: gettext("Pinnwand"),
        lambda: gettext("Neue Beiträge auf der Pinnwand"),
        _pinboard_available,
        _pinboard,
    ),
    Tile(
        "meine-anmeldungen",
        lambda: gettext("Meine Anmeldungen"),
        lambda: gettext("Veranstaltungen, für die du angemeldet bist"),
        _registrations_available,
        _registrations,
    ),
    Tile(
        "sammelbestellung",
        lambda: gettext("Sammelbestellung"),
        lambda: gettext("Laufende Sammelbestellungen, bei denen du noch bestellen kannst"),
        _orders_available,
        _orders,
    ),
]
