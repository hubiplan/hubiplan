"""Offene Aufgaben für die Startseite: Vorgänge, die eine Entscheidung brauchen.

Die Liste ist nur ein Einstieg; entschieden wird weiter in der jeweiligen
Fachansicht (Anfragen, Mitgliedsakte, Termin). Jede Art erscheint nur mit dem
Recht, das die Entscheidung erfordert.
"""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, ngettext
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    BILLING_EDIT,
    BILLING_VIEW,
    CIRCULARS_SEND,
    EVENTS_MANAGE,
    FINANCE_EDIT,
    MEMBERS_EDIT,
    PHOTOS_MANAGE,
    WEBSITE_MANAGE,
)
from core.api_base import OrgScopedMixin
from core.i18n import date_text
from organizations.models import Organization

LIMIT = 20
# Termine mit Zu-/Absagen, die bald stattfinden
EVENT_DAYS = 14
# Rundschreiben-Entwürfe, die so lange liegen, erscheinen unter „Zu erledigen“
DRAFT_DAYS = 7
# Der Kontoauszug des Vormonats erscheint ab diesem Tag des Monats unter „Zu erledigen“
STATEMENT_GRACE_DAYS = 5


def _person(membership) -> str:
    p = membership.person
    return f"{p.first_name} {p.last_name}"


def member_tasks(org: Organization, perms: set[str]) -> list[dict]:
    from portal.models import CancellationRequest, ChangeRequest

    from .models import TransferRequest
    from .photo_models import MemberPhoto

    items: list[dict] = []
    if MEMBERS_EDIT in perms:
        for cr in ChangeRequest.objects.filter(
            organization=org, status=ChangeRequest.Status.PENDING
        ).select_related("membership__person")[:LIMIT]:
            items.append(
                {
                    "kind": "change_request",
                    "kind_label": gettext("Datenänderung"),
                    "title": _person(cr.membership),
                    "detail": gettext("möchte eigene Daten ändern"),
                    "created_at": cr.created_at,
                    "link": "/mitglieder/anfragen/aenderungen",
                    "ref": cr.pk,
                    "membership": cr.membership_id,
                }
            )
        for c in CancellationRequest.objects.filter(
            organization=org, status=CancellationRequest.Status.PENDING
        ).select_related("membership__person")[:LIMIT]:
            items.append(
                {
                    "kind": "cancellation",
                    "kind_label": gettext("Kündigung"),
                    "title": _person(c.membership),
                    "detail": gettext("kündigt zum {date}").format(date=date_text(c.exit_date)),
                    "created_at": c.created_at,
                    "link": "/mitglieder/anfragen/kuendigungen",
                    "ref": c.pk,
                    "membership": c.membership_id,
                }
            )
        for tr in TransferRequest.objects.filter(
            from_org=org, status=TransferRequest.Status.PENDING
        ).select_related("person", "to_org")[:LIMIT]:
            items.append(
                {
                    "kind": "transfer",
                    "kind_label": gettext("Wechselanfrage"),
                    "title": f"{tr.person.first_name} {tr.person.last_name}",
                    "detail": gettext("{org} möchte aufnehmen").format(org=tr.to_org.display_name),
                    "created_at": tr.created_at,
                    "link": "/mitglieder/anfragen",
                }
            )
    if PHOTOS_MANAGE in perms:
        for photo in MemberPhoto.objects.filter(
            organization=org, status=MemberPhoto.Status.PENDING
        ).select_related("membership__person")[:LIMIT]:
            items.append(
                {
                    "kind": "photo",
                    "kind_label": gettext("Foto freigeben"),
                    "title": _person(photo.membership),
                    "detail": gettext("hat ein Foto hochgeladen"),
                    "created_at": photo.created_at,
                    "link": f"/mitglieder/{photo.membership_id}",
                    "ref": photo.pk,
                    "membership": photo.membership_id,
                }
            )
    return items


def event_tasks(org: Organization, perms: set[str]) -> list[dict]:
    from django.db.models import Count, Q

    from events.models import Event, EventResponse

    if EVENTS_MANAGE not in perms or "events" not in (org.enabled_modules or []):
        return []
    now = timezone.now()
    events = (
        Event.objects.filter(
            organization=org,
            department__isnull=True,
            rsvp_enabled=True,
            is_cancelled=False,
            starts_at__gte=now,
            starts_at__lte=now + datetime.timedelta(days=EVENT_DAYS),
        )
        .annotate(
            yes=Count("responses", filter=Q(responses__status=EventResponse.Status.YES)),
            no=Count("responses", filter=Q(responses__status=EventResponse.Status.NO)),
        )
        .order_by("starts_at")[:LIMIT]
    )
    local = timezone.localtime
    return [
        {
            "kind": "event",
            "kind_label": gettext("Rückmeldungen"),
            "title": e.title,
            "detail": gettext("am {date}: {yes} Zusagen, {no} Absagen").format(
                date=date_format(local(e.starts_at).date(), "SHORT_DATE_FORMAT", use_l10n=True),
                yes=e.yes,
                no=e.no,
            ),
            "created_at": e.starts_at,
            "link": f"/termine?termin={e.pk}&datum={local(e.starts_at):%Y-%m-%d}",
            "ref": e.pk,
        }
        for e in events
    ]


def billing_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Rechnungen und Lastschriften unter „Zu erledigen“ (UX-Audit 10.6, Menüprüfung 2 N-03).

    Dieselben Einträge zeigt die Finanzen-Übersicht (``area`` = ``finance``)."""
    from billing import sepa, services
    from billing.models import DebitRun, Invoice

    if BILLING_VIEW not in perms or "billing" not in (org.enabled_modules or []):
        return []
    today = timezone.localdate()
    short = lambda day: date_format(day, "SHORT_DATE_FORMAT", use_l10n=True)  # noqa: E731
    items: list[dict] = []
    overdue = Invoice.objects.filter(
        organization=org, status=Invoice.Status.OPEN, due_date__lt=today
    )
    n = overdue.count()
    if n:
        first = overdue.order_by("due_date").values_list("due_date", flat=True).first()
        items.append(
            {
                "kind": "invoices_overdue",
                "area": "finance",
                "kind_label": gettext("Rechnungen"),
                "title": ngettext("{n} Rechnung überfällig", "{n} Rechnungen überfällig", n).format(
                    n=n
                ),
                "detail": gettext("älteste fällig seit {date}").format(date=short(first)),
                "created_at": first,
                "link": "/finanzen/rechnungen?status=open&ueberfaellig=1",
                "highlight": True,
            }
        )
    if BILLING_EDIT not in perms:
        return items
    drafts = Invoice.objects.filter(organization=org, status=Invoice.Status.DRAFT)
    n = drafts.count()
    if n:
        items.append(
            {
                "kind": "invoices_draft",
                "area": "finance",
                "kind_label": gettext("Rechnungen"),
                "title": ngettext(
                    "{n} Entwurf noch nicht festgeschrieben",
                    "{n} Entwürfe noch nicht festgeschrieben",
                    n,
                ).format(n=n),
                "detail": gettext("prüfen und festschreiben"),
                "created_at": None,
                "link": "/finanzen/rechnungen?status=draft",
            }
        )
    n = len(services.dunning_proposals(org, today))
    if n:
        items.append(
            {
                "kind": "dunnings_due",
                "area": "finance",
                "kind_label": gettext("Mahnungen"),
                "title": ngettext(
                    "{n} Rechnung ist zu mahnen", "{n} Rechnungen sind zu mahnen", n
                ).format(n=n),
                "detail": gettext("Mahnstufe erreicht"),
                "created_at": today,
                "link": "/finanzen/rechnungen/mahnungen",
            }
        )
    sepa_on = services.settings_for(org).sepa_enabled and org.type != Organization.Type.UNIT
    if sepa_on:
        n = len(sepa.proposals(org, today))
        if n:
            items.append(
                {
                    "kind": "debits_ready",
                    "area": "finance",
                    "kind_label": gettext("Lastschriften"),
                    "title": ngettext(
                        "{n} Rechnung kann per Lastschrift eingezogen werden",
                        "{n} Rechnungen können per Lastschrift eingezogen werden",
                        n,
                    ).format(n=n),
                    "detail": gettext("Lastschriftlauf anlegen"),
                    "created_at": today,
                    "link": "/finanzen/lastschrift",
                }
            )
        for run in DebitRun.objects.filter(
            organization=org, status=DebitRun.Status.CREATED
        ).order_by("collection_date"):
            items.append(
                {
                    "kind": "debit_pending",
                    "area": "finance",
                    "kind_label": gettext("Lastschriften"),
                    "title": gettext(
                        "Lastschrift zum {date} noch nicht als bezahlt gebucht"
                    ).format(date=short(run.collection_date)),
                    "detail": gettext("über {amount} €").format(amount=f"{run.total:.2f}"),
                    "created_at": run.collection_date,
                    "link": "/finanzen/lastschrift",
                    "ref": run.pk,
                }
            )
    return items


def incoming_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Eingegangene Rechnungen, die noch geprüft werden müssen (Menüprüfung 2, N-03)."""
    from billing.models import IncomingInvoice

    if FINANCE_EDIT not in perms or "finance" not in (org.enabled_modules or []):
        return []
    pending = IncomingInvoice.objects.filter(organization=org, status="review")
    n = pending.count()
    if not n:
        return []
    first = pending.order_by("created_at").values_list("created_at", flat=True).first()
    return [
        {
            "kind": "incoming_review",
            "area": "finance",
            "kind_label": gettext("Rechnungseingang"),
            "title": ngettext(
                "{n} eingegangene Rechnung zu prüfen", "{n} eingegangene Rechnungen zu prüfen", n
            ).format(n=n),
            "detail": gettext("älteste vom {date}").format(
                date=date_format(
                    timezone.localtime(first).date(), "SHORT_DATE_FORMAT", use_l10n=True
                )
            ),
            "created_at": first,
            "link": "/finanzen/rechnungen/eingang",
        }
    ]


def bookkeeping_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Kassenführung (S-04, H3): Buchungen ohne Beleg im laufenden Geschäftsjahr und Bankkonten,
    deren Kontoauszug für den Vormonat fehlt. Nur mit dem Recht, die Kasse zu führen."""
    from django.db.models import Exists, Max, OuterRef, Subquery

    from finance.models import Account, BankStatement, Booking, Receipt

    if FINANCE_EDIT not in perms or "finance" not in (org.enabled_modules or []):
        return []
    today = timezone.localdate()
    short = lambda day: date_format(day, "SHORT_DATE_FORMAT", use_l10n=True)  # noqa: E731
    items: list[dict] = []
    year = org.fiscal_year_of(today)
    visible = Receipt.objects.filter(booking=OuterRef("pk"), hidden_at__isnull=True)
    # Wie die Prüfliste der Kassenprüfung: ohne Stornos, Umbuchungen und Teile einer Splitbuchung
    without = (
        Booking.objects.filter(
            organization=org,
            year=year,
            cancels__isnull=True,
            cancellation__isnull=True,
            split_of__isnull=True,
        )
        .exclude(kind=Booking.Kind.TRANSFER)
        .annotate(has=Exists(visible))
        .filter(has=False)
    )
    n = without.count()
    if n:
        first = without.order_by("date").values_list("date", flat=True).first()
        items.append(
            {
                "kind": "bookings_without_receipt",
                "area": "finance",
                "kind_label": gettext("Kassenbuch"),
                "title": ngettext("{n} Buchung ohne Beleg", "{n} Buchungen ohne Beleg", n).format(
                    n=n
                ),
                "detail": gettext("älteste vom {date}").format(date=short(first)),
                "created_at": first,
                "link": "/finanzen/kassenbuch?ohne_beleg=1",
            }
        )
    # Kontoauszug des Vormonats: nur für Bankkonten, deren Auszüge hier eingelesen werden
    month_start = today.replace(day=1)
    last_month_end = month_start - datetime.timedelta(days=1)
    if today.day >= STATEMENT_GRACE_DAYS:
        latest = (
            BankStatement.objects.filter(account=OuterRef("pk"), date_to__isnull=False)
            .values("account")
            .annotate(last=Max("date_to"))
            .values("last")
        )
        accounts = (
            Account.objects.filter(organization=org, is_active=True, kind=Account.Kind.BANK)
            .annotate(last=Subquery(latest[:1]))
            .filter(last__isnull=False, last__lt=last_month_end)
            .order_by("position", "name")
        )
        month = date_format(last_month_end, "F Y", use_l10n=True)
        for account in accounts:
            items.append(
                {
                    "kind": "statement_missing",
                    "area": "finance",
                    "kind_label": gettext("Kontoauszüge"),
                    "title": gettext("Kontoauszug {month} einlesen").format(month=month),
                    "detail": gettext("{account}: eingelesen bis {date}").format(
                        account=account.name, date=short(account.last)
                    ),
                    "created_at": account.last,
                    "link": "/finanzen/kontoauszuege",
                    "ref": account.pk,
                }
            )
    return items


def account_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Konten, deren Einladung abgelaufen ist (Menüprüfung 2, N-03)."""
    from access.accounts_view import account_data, collect
    from access.catalog import ROLES_MANAGE

    if ROLES_MANAGE not in perms:
        return []
    expired = [
        a
        for a in (account_data(r) for r in collect(org, perms).values())
        if a["invitation_expired"]
    ]
    if not expired:
        return []
    n = len(expired)
    return [
        {
            "kind": "accounts_expired",
            "area": "accounts",
            "kind_label": gettext("Konten"),
            "title": ngettext(
                "Einladung von {n} Konto abgelaufen", "Einladungen von {n} Konten abgelaufen", n
            ).format(n=n),
            "detail": gettext("Anmeldelink erneut senden"),
            "created_at": None,
            "link": "/einstellungen/konten?filter=expired",
        }
    ]


def booking_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Offene Belegungsanfragen, die diese Person freigeben darf (Menüprüfung M-13)."""
    from bookings import access
    from bookings.models import Booking
    from todos.access import Scope

    if org.type not in ("club", "federation") or not access.MODULES & set(
        org.enabled_modules or []
    ):
        return []
    scope = Scope(org, None, perms)
    if not access.kinds(scope):
        return []
    pending = [
        b
        for b in Booking.objects.filter(
            organization=org,
            department__isnull=True,
            item__in=access.items(scope),
            status=Booking.Status.REQUESTED,
        )
        .select_related("item")
        .order_by("starts_at")[:LIMIT]
        if access.can_manage(scope, b.item)
    ]
    local = timezone.localtime
    return [
        {
            "kind": "booking",
            "kind_label": gettext("Belegungsanfrage"),
            "title": b.item.title,
            "detail": gettext("am {date} angefragt").format(
                date=date_format(local(b.starts_at).date(), "SHORT_DATE_FORMAT", use_l10n=True)
            ),
            "created_at": b.created_at,
            "link": f"/belegung?ab={local(b.starts_at):%Y-%m-%d}",
            "ref": b.pk,
        }
        for b in pending
    ]


def website_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Zurückgehaltene Nachrichten aus dem Kontaktformular (Menüprüfung M-13)."""
    from website.contact_models import HeldMessage

    if WEBSITE_MANAGE not in perms or "website" not in (org.enabled_modules or []):
        return []
    held = HeldMessage.objects.filter(organization=org)
    n = held.count()
    if not n:
        return []
    first = held.order_by("created_at").values_list("created_at", flat=True).first()
    return [
        {
            "kind": "contact_held",
            "kind_label": gettext("Kontaktformular"),
            "title": ngettext(
                "{n} Nachricht wartet auf Freigabe", "{n} Nachrichten warten auf Freigabe", n
            ).format(n=n),
            "detail": gettext("wird nach 7 Tagen gelöscht"),
            "created_at": first,
            "link": "/webseite/kontakt",
        }
    ]


def circular_tasks(user, org: Organization, perms: set[str]) -> list[dict]:
    """Eigene Rundschreiben-Entwürfe, die seit einer Woche liegen (Menüprüfung M-13)."""
    from circulars.models import Circular

    if CIRCULARS_SEND not in perms or org.type not in ("club", "federation"):
        return []
    old = timezone.now() - datetime.timedelta(days=DRAFT_DAYS)
    drafts = Circular.objects.filter(
        organization=org,
        department__isnull=True,
        status=Circular.Status.DRAFT,
        created_by=user,
        updated_at__lt=old,
        # Muster der Verteiler sind keine echten Entwürfe, sie werden nie versendet
        list_pattern__isnull=True,
    ).order_by("updated_at")[:LIMIT]
    return [
        {
            "kind": "circular_draft",
            "kind_label": gettext("Rundschreiben"),
            "title": c.subject or gettext("Entwurf ohne Betreff"),
            "detail": gettext("Entwurf seit {date} unverändert").format(
                date=date_format(
                    timezone.localtime(c.updated_at).date(), "SHORT_DATE_FORMAT", use_l10n=True
                )
            ),
            "created_at": c.updated_at,
            "link": f"/rundschreiben/{c.pk}",
            "ref": c.pk,
        }
        for c in drafts
    ]


@extend_schema(responses=dict)
class OpenTasksView(OrgScopedMixin, APIView):
    """Offene Aufgaben der Organisation, nach den Rechten des Benutzers."""

    def get(self, request, org_id: int):
        org, perms = self.org, self.org_permissions
        from admission.open_tasks import application_tasks
        from entries.open_tasks import entry_tasks
        from helpers.open_tasks import helper_tasks
        from meetings.open_tasks import meeting_tasks
        from obligations.open_tasks import obligation_tasks
        from organizations.setup_status import setup_tasks
        from qualifications.open_tasks import qualification_tasks
        from todos.open_tasks import todo_tasks

        # Bereich je Quelle: Die Finanzen-Übersicht zeigt nur „finance“ (Menüprüfung 2, N-03)
        sources = [
            (
                "members",
                lambda: (
                    member_tasks(org, perms)
                    if org.keeps_members and "members" in (org.enabled_modules or [])
                    else []
                ),
            ),
            (
                "members",
                lambda: (
                    application_tasks(request.user, org, perms)
                    if "members" in (org.enabled_modules or [])
                    else []
                ),
            ),
            ("members", lambda: qualification_tasks(org, perms)),
            ("events", lambda: event_tasks(org, perms)),
            (
                "finance",
                lambda: (
                    billing_tasks(org, perms)
                    + incoming_tasks(org, perms)
                    + bookkeeping_tasks(org, perms)
                ),
            ),
            ("bookings", lambda: booking_tasks(org, perms)),
            ("website", lambda: website_tasks(org, perms)),
            ("circulars", lambda: circular_tasks(request.user, org, perms)),
            ("accounts", lambda: account_tasks(org, perms)),
            ("meetings", lambda: meeting_tasks(org, perms)),
            ("helpers", lambda: helper_tasks(org, perms)),
            ("obligations", lambda: obligation_tasks(request.user, org, perms)),
            ("entries", lambda: entry_tasks(org, perms)),
            ("todos", lambda: todo_tasks(request.user, org, perms)),
            # Unvollständige Pflichtpunkte der Einrichtung (S-02 + S-04)
            ("setup", lambda: setup_tasks(org, perms)),
        ]
        items: list[dict] = []
        for area, load in sources:
            for item in load():
                item.setdefault("area", area)
                items.append(item)
        items.sort(key=lambda item: not item.get("highlight", False))
        return Response({"items": items})
