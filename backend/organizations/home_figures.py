"""Kennzahlen der Startseite je Rolle (Konzept S-04, Schritt H2).

Jede Kennzahl erscheint nur mit dem Recht, das auch ihre Fachseite zum Lesen braucht. Die
Rolle ergibt sich aus den Rechten: Kasse (Finanzen), Vorstand (Mitglieder), Schriftführung
(Versammlungen). Reihenfolge = Vorrang; die Startseite zeigt höchstens drei. Die Werte werden
kurz zwischengespeichert, damit nicht jeder Aufruf der Startseite alle Summen neu bildet.
"""

from __future__ import annotations

import datetime
import hashlib
from decimal import Decimal

from django.core.cache import cache
from django.db.models import F, OuterRef, Subquery, Sum
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import get_language, gettext
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import BILLING_VIEW, FINANCE_VIEW, MEMBERS_EDIT, MEMBERS_VIEW
from core.api_base import OrgScopedMixin
from portal.views import DepartmentScopedMixin

from .models import Organization

CACHE_SECONDS = 60
ZERO = Decimal("0")


def _money(label: str, value: Decimal, link: str, detail: str = "") -> dict:
    return {
        "kind": "money",
        "label": label,
        "value": f"{value:.2f}",
        "detail": detail,
        "link": link,
    }


def _count(label: str, value: int, link: str, detail: str = "") -> dict:
    return {"kind": "count", "label": label, "value": value, "detail": detail, "link": link}


def _date(label: str, day: datetime.date, link: str, detail: str = "") -> dict:
    return {
        "kind": "date",
        "label": label,
        "value": day.isoformat(),
        "detail": detail,
        "link": link,
    }


def finance_figures(org: Organization, perms: set[str]) -> list[dict]:
    from billing.models import Invoice
    from finance import services
    from finance.models import Account, BankStatement

    modules = set(org.enabled_modules or [])
    out: list[dict] = []
    if FINANCE_VIEW in perms and "finance" in modules:
        accounts = list(Account.objects.filter(organization=org, is_active=True))
        cash = [a for a in accounts if a.kind == Account.Kind.CASH]
        if cash:
            balances = services.balances(org.pk)
            out.append(
                {
                    "key": "cash",
                    **_money(
                        gettext("Barkasse heute"),
                        sum((balances.get(a.pk, ZERO) for a in cash), ZERO),
                        "/finanzen/kassenbuch",
                    ),
                }
            )
        # Endsaldo des jüngsten Auszugs je Bankkonto
        latest = BankStatement.objects.filter(
            account=OuterRef("pk"), date_to__isnull=False, closing_balance__isnull=False
        ).order_by("-date_to", "-created_at")
        banks = list(
            Account.objects.filter(organization=org, is_active=True, kind=Account.Kind.BANK)
            .annotate(
                closing=Subquery(latest.values("closing_balance")[:1]),
                closing_date=Subquery(latest.values("date_to")[:1]),
            )
            .filter(closing__isnull=False)
        )
        if banks:
            oldest = min(b.closing_date for b in banks)
            detail = gettext("Stand {date}").format(
                date=date_format(oldest, "SHORT_DATE_FORMAT", use_l10n=True)
            )
            if len(banks) == 1:
                detail = f"{banks[0].name} · {detail}"
            out.append(
                {
                    "key": "bank",
                    **_money(
                        gettext("Konto laut letztem Auszug"),
                        sum((b.closing for b in banks), ZERO),
                        "/finanzen/kontoauszuege",
                        detail,
                    ),
                }
            )
    if BILLING_VIEW in perms and "billing" in modules:
        open_fees = Invoice.objects.filter(
            organization=org, status=Invoice.Status.OPEN, run__isnull=False
        ).aggregate(s=Sum(F("total") - F("paid") - F("prepaid")))["s"]
        out.append(
            {
                "key": "open_fees",
                **_money(
                    gettext("Offene Beiträge"),
                    max(open_fees or ZERO, ZERO),
                    "/finanzen/rechnungen?status=open",
                ),
            }
        )
    return out


def member_figures(org: Organization, perms: set[str]) -> list[dict]:
    from members.views import member_queryset
    from portal.models import ChangeRequest

    if not org.keeps_members or "members" not in (org.enabled_modules or []):
        return []
    out: list[dict] = []
    if MEMBERS_VIEW in perms:
        out.append(
            {
                "key": "members_active",
                **_count(
                    gettext("Mitglieder heute"),
                    member_queryset(org).filter(is_current=True).count(),
                    "/mitglieder",
                ),
            }
        )
    if MEMBERS_EDIT in perms:
        out.append(
            {
                "key": "change_requests",
                **_count(
                    gettext("Datenänderungen offen"),
                    ChangeRequest.objects.filter(
                        organization=org, status=ChangeRequest.Status.PENDING
                    ).count(),
                    "/mitglieder/anfragen/aenderungen",
                ),
            }
        )
    return out


def meeting_figures(org: Organization, perms: set[str]) -> list[dict]:
    from meetings.access import MODULE, VIEW
    from meetings.models import Meeting

    if VIEW not in perms and "meetings.edit" not in perms:
        return []
    if MODULE not in (org.enabled_modules or []):
        return []
    upcoming = (
        Meeting.objects.filter(
            organization=org, department__isnull=True, event__starts_at__gte=timezone.now()
        )
        .exclude(status=Meeting.Status.CANCELLED)
        .select_related("event", "kind")
        .order_by("event__starts_at")
        .first()
    )
    if upcoming is None:
        return []
    day = timezone.localtime(upcoming.event.starts_at).date()
    link = f"/versammlungen?versammlung={upcoming.pk}"
    out = [
        {
            "key": "next_meeting",
            **_date(gettext("Nächste Versammlung"), day, link, upcoming.event.title),
        }
    ]
    if upcoming.status == Meeting.Status.DRAFT:
        invite_by = day - datetime.timedelta(days=upcoming.kind.invite_days)
        out.append(
            {
                "key": "invite_by",
                **_date(gettext("Einladen bis"), invite_by, link, upcoming.event.title),
            }
        )
    return out


def home_figures(org: Organization, perms: set[str], finance_first: bool = True) -> list[dict]:
    """Kennzahlen nach Vorrang der Rollen: Kasse vor Vorstand vor Schriftführung. Wer kein
    Kassenamt hat (``finance_first`` falsch), sieht die Zahlen des Vorstands zuerst."""
    if org.type not in (Organization.Type.CLUB, Organization.Type.FEDERATION):
        return []
    key = "home-figures:{}:{}:{}:{}:{}".format(
        org.pk,
        int(finance_first),
        get_language() or "",
        timezone.localdate().isoformat(),
        hashlib.sha256(",".join(sorted(perms)).encode()).hexdigest()[:16],
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    finance = finance_figures(org, perms)
    rest = member_figures(org, perms) + meeting_figures(org, perms)
    figures = finance + rest if finance_first else rest + finance
    cache.set(key, figures, CACHE_SECONDS)
    return figures


@extend_schema(responses=dict)
class HomeFiguresView(OrgScopedMixin, APIView):
    """Kennzahlen der Startseite, nach den Rechten des Benutzers."""

    def get(self, request, org_id: int):
        from access import preview
        from access.permissions import home_focus

        current = preview.current()
        codes = (
            preview.role_permissions(self.org, current.role_id)
            if current and current.org_id == self.org.pk
            else None
        )
        focus = home_focus(request.user, self.org, codes)
        return Response(
            {"figures": home_figures(self.org, self.org_permissions, "finance" in focus)}
        )


@extend_schema(responses=dict)
class DeptHomeFiguresView(DepartmentScopedMixin, APIView):
    """Kennzahl im Arbeitsbereich einer Untereinheit: Mitglieder der Einheit."""

    def get(self, request, dept_id: int):
        n = self.dept_members().count()
        return Response(
            {"figures": [{"key": "dept_members", **_count(gettext("Mitglieder"), n, "/abteilung")}]}
        )
