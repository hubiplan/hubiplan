"""Stand der Einrichtung (Konzept S-02): je Einrichtungspunkt, ob etwas angelegt ist.

Die Übersicht Einstellungen › Einrichtung zeigt alle Einrichtungsseiten der aktiven Module;
dieser Endpunkt liefert dazu den Stand, nach Pfad der Seite im Frontend. Jeder Punkt erscheint
nur mit dem Recht, das auch seine Seite zum Lesen braucht. Pflichtpunkte zählen für den
Fortschritt „9 von 12 erledigt“; fehlen welche, erscheinen sie unter „Zu erledigen“.
"""

from __future__ import annotations

from django.utils.translation import gettext, ngettext
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    BILLING_VIEW,
    EVENTS_MANAGE,
    FINANCE_VIEW,
    MEMBERS_VIEW,
    SETTINGS_VIEW,
    THEME_VIEW,
)
from core.api_base import OrgScopedMixin

from .models import Organization

# Pfad der Übersicht im Frontend
OVERVIEW = "/einstellungen/einrichtung"
# Das Impressum steht auf der Startseite schon unter „Hinweise“ (S-04)
NOT_IN_TASKS = {"/einstellungen/impressum"}


def _point(required: bool, done: bool, count: int | None = None, missing=None) -> dict:
    point = {"required": required, "done": done}
    if count is not None:
        point["count"] = count
    if missing:
        point["missing"] = list(missing)
    return point


def _counted(required: bool, count: int) -> dict:
    return _point(required, count > 0, count)


def _general(org: Organization, perms: set[str]) -> dict[str, dict]:
    from . import imprint as imprint_service

    points: dict[str, dict] = {}
    if SETTINGS_VIEW in perms:
        address = bool(org.street and org.postal_code and org.city)
        points["/einstellungen/organisation"] = _point(
            True, address, missing=[] if address else [gettext("Anschrift")]
        )
        owner, effective = imprint_service.owner_of(org)
        missing = imprint_service.missing(owner, effective)
        points["/einstellungen/impressum"] = _point(True, not missing, missing=missing)
    if THEME_VIEW in perms:
        points["/einstellungen/erscheinungsbild"] = _point(
            False, bool(org.primary_color or org.logo)
        )
    return points


def _members(org: Organization, perms: set[str]) -> dict[str, dict]:
    from customfields.models import FieldDefinition
    from members.models import HonoraryTitle, MemberType

    if MEMBERS_VIEW not in perms or "members" not in (org.enabled_modules or []):
        return {}
    points = {
        "/mitglieder/einrichtung/zusatzfelder": _counted(
            False, FieldDefinition.objects.filter(organization=org).count()
        ),
    }
    if org.keeps_members:
        points["/mitglieder/einrichtung/mitgliedsarten"] = _counted(
            True, MemberType.objects.filter(organization=org).count()
        )
    if "awards" in (org.enabled_modules or []):
        points["/mitglieder/einrichtung/ehrungen"] = _counted(
            False, HonoraryTitle.objects.filter(organization=org).count()
        )
    return points


def _events(org: Organization, perms: set[str]) -> dict[str, dict]:
    from events.models import EventCategory

    if EVENTS_MANAGE not in perms or "events" not in (org.enabled_modules or []):
        return {}
    return {
        "/termine/einrichtung/kategorien": _counted(
            False, EventCategory.objects.filter(organization=org, is_active=True).count()
        )
    }


def _finance(org: Organization, perms: set[str]) -> dict[str, dict]:
    from billing.models import BillingSettings, DunningLevel, FeeRate
    from finance.models import Account, Category, DonationSettings

    modules = set(org.enabled_modules or [])
    points: dict[str, dict] = {}
    finance = FINANCE_VIEW in perms and "finance" in modules
    billing = BILLING_VIEW in perms and "billing" in modules
    if finance:
        points["/finanzen/einrichtung/konten"] = _counted(
            True, Account.objects.filter(organization=org, is_active=True).count()
        )
        points["/finanzen/einrichtung/kategorien"] = _counted(
            True, Category.objects.filter(organization=org, is_active=True).count()
        )
        if "donations" in modules:
            ds = DonationSettings.objects.filter(organization=org).first()
            enabled = bool(ds and ds.enabled)
            filled = bool(ds and ds.tax_office and ds.tax_number and ds.notice_date)
            # Pflicht nur, wenn der Verein Zuwendungsbestätigungen ausstellen will
            points["/finanzen/einrichtung/zuwendungen"] = _point(enabled, filled)
    if billing:
        if org.keeps_members:
            points["/finanzen/einrichtung/beitraege"] = _counted(
                True, FeeRate.objects.filter(organization=org).count()
            )
        points["/finanzen/einrichtung/mahnstufen"] = _counted(
            True, DunningLevel.objects.filter(organization=org).count()
        )
        bs = BillingSettings.objects.filter(organization=org).first()
        points["/finanzen/einrichtung/rechnung"] = _point(True, bool(bs and bs.account_id))
    return points


def setup_status(org: Organization, perms: set[str]) -> dict[str, dict]:
    """Stand je Einrichtungspunkt (Pfad der Seite), nur Punkte mit Leserecht."""
    if org.type not in (Organization.Type.CLUB, Organization.Type.FEDERATION):
        return {}
    points: dict[str, dict] = {}
    for part in (_general, _members, _events, _finance):
        points.update(part(org, perms))
    return points


def setup_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Unvollständige Pflichtpunkte als ein Eintrag unter „Zu erledigen“ (S-02 + S-04)."""
    points = setup_status(org, perms)
    open_points = [
        path
        for path, p in points.items()
        if p["required"] and not p["done"] and path not in NOT_IN_TASKS
    ]
    if not open_points:
        return []
    n = len(open_points)
    return [
        {
            "kind": "setup_incomplete",
            "area": "setup",
            "kind_label": gettext("Einrichtung"),
            "title": ngettext(
                "{n} Einrichtungspunkt fehlt noch",
                "{n} Einrichtungspunkte fehlen noch",
                n,
            ).format(n=n),
            "detail": gettext("Übersicht der Einrichtung öffnen"),
            "created_at": None,
            "link": OVERVIEW,
            "paths": open_points,
        }
    ]


@extend_schema(responses=dict)
class SetupStatusView(OrgScopedMixin, APIView):
    """Stand der Einrichtung je Punkt, nach den Rechten des Benutzers."""

    def get(self, request, org_id: int):
        return Response({"items": setup_status(self.org, self.org_permissions)})
