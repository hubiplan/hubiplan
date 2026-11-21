"""Kacheln für die Verwaltung (Vorstand, Kasse, Schriftführung) mit ihrem Anlass."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, ngettext

from access.modules import module_on

from .base import Content, Figure, Row, Tile, count, day_text, euro, today, when_text

ZERO = Decimal("0.00")
# Anlässe (docs/startseite-kacheln.md)
REGISTRATION_DAYS = 14
MEETING_DAYS = 42
WORKHOURS_LAST_DAYS = 61
ROWS = 5
ORDER_DAYS = 7


@dataclass
class OrgContext:
    org: object
    perms: set[str]
    user: object

    def has(self, *codes: str) -> bool:
        return any(c in self.perms for c in codes)

    @property
    def club_like(self) -> bool:
        return self.org.type in ("club", "federation")


def _event_link(event) -> str:
    day = timezone.localtime(event.starts_at).date()
    return f"/termine?termin={event.pk}&datum={day:%Y-%m-%d}"


# --- 1 Kasse auf einen Blick -----------------------------------------------------------------


def _cash_available(ctx: OrgContext) -> bool:
    return ctx.club_like and module_on(ctx.org, "finance") and ctx.has("finance.view")


def _cash(ctx: OrgContext) -> Content:
    from billing.models import Invoice
    from finance.models import Account
    from finance.services import balances

    org = ctx.org
    c = Content(link="/finanzen", link_label=gettext("Zu den Finanzen"))
    accounts = list(
        Account.objects.filter(organization=org, is_active=True).order_by("position", "name")
    )
    sums = balances(org.pk)
    minus = False
    for a in accounts[:4]:
        value = sums.get(a.pk, ZERO)
        minus = minus or value < 0
        c.figures.append(Figure(a.name, euro(value), "bad" if value < 0 else None))
    if any(sums.get(a.pk, ZERO) < 0 for a in accounts[4:]):
        minus = True
    if not accounts:
        c.text = gettext("Noch keine Konten angelegt.")
    if module_on(org, "billing") and ctx.has("billing.view"):
        open_ = Invoice.objects.filter(organization=org, status=Invoice.Status.OPEN)
        total = sum((i.outstanding for i in open_), ZERO)
        n = open_.count()
        c.figures.append(
            Figure(
                ngettext("Offene Forderung", "Offene Forderungen", n),
                euro(total),
                "warn" if open_.filter(due_date__lt=today()).exists() else None,
            )
        )
        from members.open_tasks import billing_tasks

        for item in billing_tasks(org, ctx.perms):
            if item["kind"] in ("debits_ready", "debit_pending"):
                c.rows.append(Row(item["title"], item.get("detail", ""), item["link"], "warn"))
        if c.rows:
            c.reason = gettext("Eine Lastschrift ist fällig.")
    if minus:
        c.reason = gettext("Ein Konto steht im Minus.")
    return c


# --- 2 Laufende Anmeldungen ------------------------------------------------------------------


def _registrations_available(ctx: OrgContext) -> bool:
    from registrations.services import module_on as reg_on

    return ctx.club_like and reg_on(ctx.org) and ctx.has("registrations.view")


def _registrations(ctx: OrgContext) -> Content:
    from billing.models import Invoice
    from registrations import services
    from registrations.models import Registration, RegistrationSetup

    now = timezone.now()
    setups = list(
        RegistrationSetup.objects.filter(organization=ctx.org, event__starts_at__gte=now)
        .exclude(event__is_cancelled=True)
        .select_related("event")
        .order_by("event__starts_at")[:ROWS]
    )
    c = Content(link="/termine", link_label=gettext("Zum Kalender"))
    soon = now + datetime.timedelta(days=REGISTRATION_DAYS)
    for s in setups:
        taken = services.taken(s)
        parts = [ngettext("{n} angemeldet", "{n} angemeldet", taken).format(n=count(taken))]
        free = services.free(s)
        if free is not None:
            parts.append(ngettext("{n} Platz frei", "{n} Plätze frei", free).format(n=count(free)))
        unpaid = Registration.objects.filter(
            setup=s, status=Registration.Status.REGISTERED, invoice__status=Invoice.Status.OPEN
        ).count()
        if unpaid:
            parts.append(ngettext("{n} unbezahlt", "{n} unbezahlt", unpaid).format(n=count(unpaid)))
        waiting = services.waiting_count(s)
        if waiting:
            parts.append(gettext("{n} auf der Warteliste").format(n=count(waiting)))
        c.rows.append(
            Row(
                f"{s.event.title} · {when_text(s.event.starts_at)}",
                " · ".join(parts),
                _event_link(s.event),
                "warn" if unpaid else None,
            )
        )
        if s.event.starts_at <= soon and not c.reason:
            c.reason = gettext("„{title}“ ist bald.").format(title=s.event.title)
    if not setups:
        c.text = gettext("Zurzeit keine Veranstaltung mit Anmeldung.")
    return c


# --- 3 Verein in Zahlen ----------------------------------------------------------------------


def _figures_available(ctx: OrgContext) -> bool:
    return ctx.org.type == "club" and module_on(ctx.org, "members") and ctx.has("members.view")


def _figures(ctx: OrgContext) -> Content:
    from members.models import MembershipPeriod

    org, day = ctx.org, today()
    year = org.fiscal_year_of(day)
    start, _end = org.fiscal_range(year)
    periods = MembershipPeriod.objects.filter(organization=org)
    current = (
        periods.filter(entry_date__lte=day)
        .filter(Q(exit_date__isnull=True) | Q(exit_date__gt=day))
        .values("membership_id")
        .distinct()
        .count()
    )
    entries = (
        periods.filter(entry_date__gte=start, entry_date__lte=day)
        .values("membership_id")
        .distinct()
        .count()
    )
    exits = (
        periods.filter(exit_date__gte=start, exit_date__lte=day)
        .values("membership_id")
        .distinct()
        .count()
    )
    label = org.fiscal_label(year)
    c = Content(
        figures=[
            Figure(gettext("Mitglieder"), count(current)),
            Figure(
                gettext("Eintritte {year}").format(year=label),
                count(entries),
                "good" if entries else None,
            ),
            Figure(gettext("Austritte {year}").format(year=label), count(exits)),
        ],
        link="/mitglieder/entwicklung/stichtag",
        link_label=gettext("Zur Stichtagsstatistik"),
    )
    if day.month == 1:
        c.reason = gettext("Die Stichtagsmeldung steht an.")
    return c


# --- 4 Belegung diese Woche ------------------------------------------------------------------


def _bookings_scope(ctx: OrgContext):
    from bookings import access
    from todos.access import Scope

    if not ctx.club_like or not access.MODULES & set(ctx.org.enabled_modules or []):
        return None
    scope = Scope(ctx.org, None, ctx.perms)
    return scope if access.kinds(scope) else None


def _bookings_available(ctx: OrgContext) -> bool:
    return _bookings_scope(ctx) is not None


def _bookings(ctx: OrgContext) -> Content:
    from bookings import access
    from bookings.models import Booking
    from bookings.services import occurrences

    scope = _bookings_scope(ctx)
    now = timezone.now()
    end = now + datetime.timedelta(days=7)
    qs = (
        Booking.objects.filter(
            organization=ctx.org,
            department__isnull=True,
            item__in=access.items(scope),
            status__in=[Booking.Status.CONFIRMED, Booking.Status.REQUESTED],
            starts_at__lt=end,
        )
        .filter(Q(repeat="none") | Q(repeat_until__isnull=True) | Q(repeat_until__gte=now.date()))
        .filter(Q(ends_at__gt=now) | ~Q(repeat="none"))
        .select_related("item")
    )
    found = []
    for b in qs:
        for _orig, begin, finish in occurrences(b, now, end):
            if begin < end and finish > now:
                found.append((begin, finish, b))
    found.sort(key=lambda x: x[0])
    c = Content(link="/belegung", link_label=gettext("Zur Belegung"))
    day = today()
    for begin, finish, b in found[:ROWS]:
        detail = when_text(begin) + f"–{timezone.localtime(finish):%H:%M}"
        if b.status == Booking.Status.REQUESTED:
            detail += " · " + gettext("angefragt")
        c.rows.append(
            Row(
                b.item.title,
                detail,
                f"/belegung?ab={timezone.localtime(begin):%Y-%m-%d}",
                "warn" if b.status == Booking.Status.REQUESTED else None,
            )
        )
    if len(found) > ROWS:
        c.text = gettext("und {n} weitere").format(n=count(len(found) - ROWS))
    if not found:
        c.text = gettext("In den nächsten sieben Tagen ist nichts belegt.")
    first = timezone.localtime(found[0][0]).date() if found else None
    if first == day:
        c.reason = gettext("Heute ist etwas belegt.")
    elif first == day + datetime.timedelta(days=1):
        c.reason = gettext("Morgen ist etwas belegt.")
    return c


# --- 5 Arbeitsstunden-Stand ------------------------------------------------------------------


def _workhours_available(ctx: OrgContext) -> bool:
    from billing import workhours

    return ctx.org.type == "club" and ctx.has("billing.view") and workhours.active(ctx.org)


def _workhours(ctx: OrgContext) -> Content:
    from billing import workhours

    org, day = ctx.org, today()
    year = org.fiscal_year_of(day)
    _start, end = org.fiscal_range(year)
    rows = list(workhours.balances(org, year).values())
    done = sum(1 for b in rows if b.missing <= 0)
    missing = [b for b in rows if b.missing > 0]
    amount = sum((b.amount for b in missing), ZERO)
    c = Content(
        figures=[
            Figure(
                gettext("Soll erfüllt"),
                f"{count(done)} / {count(len(rows))}",
                "good" if rows and done == len(rows) else None,
            ),
            Figure(gettext("Noch offen"), count(len(missing)), "warn" if missing else None),
            Figure(gettext("Ersatzbeitrag bisher"), euro(amount)),
        ],
        text=gettext("Stand im Geschäftsjahr {year}, das am {date} endet.").format(
            year=org.fiscal_label(year), date=day_text(end)
        ),
        link="/finanzen/beitraege",
        link_label=gettext("Zu den Beitragsregeln"),
    )
    if missing and (end - day).days < WORKHOURS_LAST_DAYS:
        c.reason = gettext("Das Geschäftsjahr endet am {date}.").format(date=day_text(end))
    return c


# --- 6 Haushaltsplan: Plan gegen Ist ---------------------------------------------------------


def _budget_available(ctx: OrgContext) -> bool:
    from finance.models import Budget

    if not (ctx.club_like and module_on(ctx.org, "finance") and ctx.has("finance.view")):
        return False
    year = ctx.org.fiscal_year_of(today())
    return Budget.objects.filter(organization=ctx.org, year=year).exists()


def _budget(ctx: OrgContext) -> Content:
    from finance.budget import report

    org = ctx.org
    data = report(org, org.fiscal_year_of(today()))
    inc, exp = data["totals"]["income"], data["totals"]["expense"]
    c = Content(
        figures=[
            Figure(
                gettext("Einnahmen"),
                gettext("{actual} von {plan}").format(
                    actual=euro(inc["actual"] or ZERO), plan=euro(inc["plan"])
                ),
            ),
            Figure(
                gettext("Ausgaben"),
                gettext("{actual} von {plan}").format(
                    actual=euro(exp["actual"] or ZERO), plan=euro(exp["plan"])
                ),
                "bad" if (exp["actual"] or ZERO) > exp["plan"] else None,
            ),
        ],
        link="/finanzen/haushaltsplan",
        link_label=gettext("Zum Haushaltsplan"),
    )
    if data.get("elapsed_percent") is not None:
        c.text = gettext("{n} % des Geschäftsjahres sind vorbei.").format(n=data["elapsed_percent"])
    over = [
        ln
        for ln in data["lines"]
        if ln["kind"] == "expense" and ln["actual"] is not None and ln["actual"] > ln["amount"]
    ]
    over.sort(key=lambda ln: ln["actual"] - ln["amount"], reverse=True)
    for ln in over[:3]:
        name = ln["category_name"] + (
            f" ({ln['department_name']})" if ln["department_name"] else ""
        )
        c.rows.append(
            Row(
                name,
                gettext("{actual} von {plan}").format(
                    actual=euro(ln["actual"]), plan=euro(ln["amount"])
                ),
                "/finanzen/haushaltsplan",
                "bad",
            )
        )
    if over:
        c.reason = gettext("Eine Position liegt über dem Plan.")
    return c


# --- 7 Umfragen und Pinnwand -----------------------------------------------------------------


def _surveys_available(ctx: OrgContext) -> bool:
    return ctx.org.type == "club" and (
        (module_on(ctx.org, "surveys") and ctx.has("surveys.view", "surveys.edit"))
        or (module_on(ctx.org, "pinboard") and ctx.has("pinboard.view", "pinboard.edit"))
    )


def _surveys(ctx: OrgContext) -> Content:
    org = ctx.org
    now = timezone.now()
    c = Content()
    if module_on(org, "surveys") and ctx.has("surveys.view", "surveys.edit"):
        from surveys import services
        from surveys.models import Survey

        running = list(
            Survey.objects.filter(organization=org, status=Survey.Status.OPEN)
            .filter(Q(closes_at__isnull=True) | Q(closes_at__gt=now))
            .order_by("closes_at", "pk")[:ROWS]
        )
        answers = services.counts_by_survey(running)
        for s in running:
            n = answers.get(s.pk, 0)
            detail = ngettext("{n} Antwort", "{n} Antworten", n).format(n=count(n))
            if s.closes_at:
                detail += " · " + gettext("endet {when}").format(when=when_text(s.closes_at))
            c.rows.append(Row(s.title, detail, f"/umfragen?umfrage={s.pk}"))
        if running:
            c.reason = gettext("Eine Umfrage läuft.")
        c.link, c.link_label = "/umfragen", gettext("Zu den Umfragen")
    if module_on(org, "pinboard") and ctx.has("pinboard.view", "pinboard.edit"):
        from pinboard.models import Notice
        from pinboard.services import active

        recent = active(Notice.objects.filter(organization=org)).filter(
            created_at__gte=now - datetime.timedelta(days=14)
        )
        n = recent.count()
        c.figures.append(Figure(gettext("Neu auf der Pinnwand (14 Tage)"), count(n)))
        if not c.link:
            c.link, c.link_label = "/pinnwand", gettext("Zur Pinnwand")
    if not c.rows and module_on(org, "surveys") and ctx.has("surveys.view", "surveys.edit"):
        c.text = gettext("Zurzeit läuft keine Umfrage.")
    return c


# --- 8 Nächste Versammlung -------------------------------------------------------------------


def _meeting_available(ctx: OrgContext) -> bool:
    return (
        ctx.club_like
        and module_on(ctx.org, "meetings")
        and ctx.has("meetings.view", "meetings.edit")
    )


def _meeting(ctx: OrgContext) -> Content:
    from django.db.models import Count

    from meetings.models import Meeting, Motion

    day = today()
    m = (
        Meeting.objects.filter(organization=ctx.org, department__isnull=True)
        .exclude(status__in=[Meeting.Status.DONE, Meeting.Status.CANCELLED])
        .filter(event__starts_at__date__gte=day)
        .select_related("event", "kind")
        .annotate(motions_n=Count("motions", filter=~Q(motions__status=Motion.Status.WITHDRAWN)))
        .order_by("event__starts_at")
        .first()
    )
    c = Content(link="/versammlungen", link_label=gettext("Zu den Versammlungen"))
    if m is None:
        c.text = gettext("Keine Versammlung geplant.")
        return c
    start = timezone.localtime(m.event.starts_at).date()
    link = f"/versammlungen?versammlung={m.pk}"
    c.rows.append(
        Row(m.event.title, when_text(m.event.starts_at) + " · " + m.get_status_display(), link)
    )
    if m.status == Meeting.Status.DRAFT:
        invite_by = start - datetime.timedelta(days=m.kind.invite_days)
        c.figures.append(
            Figure(
                gettext("Einladen bis"), day_text(invite_by), "bad" if day >= invite_by else None
            )
        )
    c.figures.append(Figure(gettext("Anträge"), count(m.motions_n)))
    c.figures.append(Figure(gettext("Noch Tage"), count((start - day).days)))
    c.link = link
    if (start - day).days <= MEETING_DAYS:
        c.reason = gettext("Die nächste Versammlung ist am {date}.").format(date=day_text(start))
    return c


# --- 9 Sammelbestellungen --------------------------------------------------------------------


def _orders_available(ctx: OrgContext) -> bool:
    return (
        ctx.org.type == "club"
        and module_on(ctx.org, "orders")
        and ctx.has("orders.view", "orders.edit")
    )


def _orders(ctx: OrgContext) -> Content:
    from django.db.models import Count

    from orders.models import OrderCampaign

    day = today()
    running = list(
        OrderCampaign.objects.filter(
            organization=ctx.org,
            published_at__isnull=False,
            closed_at__isnull=True,
            deadline__gte=day,
        )
        .annotate(orders_n=Count("orders"))
        .order_by("deadline", "pk")[:ROWS]
    )
    c = Content(link="/bestellungen", link_label=gettext("Zu den Bestellungen"))
    for o in running:
        soon = (o.deadline - day).days <= ORDER_DAYS
        detail = (
            gettext("bis {date}").format(date=day_text(o.deadline))
            + " · "
            + ngettext("{n} Bestellung", "{n} Bestellungen", o.orders_n).format(n=count(o.orders_n))
        )
        c.rows.append(Row(o.title, detail, "/bestellungen", "warn" if soon else None))
        if soon and not c.reason:
            c.reason = gettext("Bestellschluss für „{title}“ ist am {date}.").format(
                title=o.title, date=day_text(o.deadline)
            )
    if not running:
        c.text = gettext("Zurzeit läuft keine Sammelbestellung.")
    return c


TILES: list[Tile] = [
    Tile(
        "kasse",
        lambda: gettext("Kasse auf einen Blick"),
        lambda: gettext("Kontostände, offene Forderungen, fällige Lastschrift"),
        _cash_available,
        _cash,
    ),
    Tile(
        "anmeldungen",
        lambda: gettext("Laufende Anmeldungen"),
        lambda: gettext("Angemeldet, freie Plätze und unbezahlt je Veranstaltung"),
        _registrations_available,
        _registrations,
    ),
    Tile(
        "verein-zahlen",
        lambda: gettext("Verein in Zahlen"),
        lambda: gettext("Mitglieder, Eintritte und Austritte im Geschäftsjahr"),
        _figures_available,
        _figures,
    ),
    Tile(
        "belegung",
        lambda: gettext("Belegung diese Woche"),
        lambda: gettext("Wer Vereinsheim, Räume oder Material in den nächsten sieben Tagen nutzt"),
        _bookings_available,
        _bookings,
    ),
    Tile(
        "arbeitsstunden",
        lambda: gettext("Arbeitsstunden-Stand"),
        lambda: gettext("Wer das Soll erfüllt hat und wie viel Ersatzbeitrag sich ergibt"),
        _workhours_available,
        _workhours,
    ),
    Tile(
        "haushalt",
        lambda: gettext("Haushaltsplan: Plan und Ist"),
        lambda: gettext("Einnahmen und Ausgaben gegen den Plan, Positionen über Plan"),
        _budget_available,
        _budget,
    ),
    Tile(
        "umfragen-pinnwand",
        lambda: gettext("Umfragen und Pinnwand"),
        lambda: gettext("Laufende Umfragen mit Rücklauf, neue Beiträge"),
        _surveys_available,
        _surveys,
    ),
    Tile(
        "versammlung",
        lambda: gettext("Nächste Versammlung"),
        lambda: gettext("Datum, Einladungsfrist und Anträge"),
        _meeting_available,
        _meeting,
    ),
    Tile(
        "sammelbestellungen",
        lambda: gettext("Sammelbestellungen"),
        lambda: gettext("Laufende Sammelbestellungen mit Bestellschluss und Zahl der Bestellungen"),
        _orders_available,
        _orders,
    ),
]
