"""Wer welche Buchungskalender sieht, bucht und freigibt.

- Sehen: Leserecht auf die Art des Objekts (Material bzw. Infrastruktur) oder „Belegung“
  (``bookings.view``) für Objekte mit Buchungskalender.
- Buchen: ``bookings.view`` oder Bearbeitungsrecht auf das Objekt. Verlangt das Objekt eine
  Freigabe, ist die Buchung ohne Freigaberecht zunächst eine Anfrage.
- Freigeben und für andere eintragen: ``bookings.edit`` oder Bearbeitungsrecht auf das Objekt.
"""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from materials.access import AREAS
from organizations.models import Organization
from todos.access import Scope

MODULES = {"material", "infrastructure"}


def scope_for(user, org_id=None, dept_id=None):
    if dept_id is not None:
        from portal.services import department_contexts

        ctx = department_contexts(user).get(int(dept_id))
        if ctx is None:
            raise NotFound()
        scope = Scope(ctx.club, ctx.department.pk, ctx.permissions)
    else:
        org = get_object_or_404(Organization, pk=org_id, type__in=["club", "federation"])
        scope = Scope(org, None, permissions_in(user, org))
    if not MODULES & set(scope.org.enabled_modules or []):
        raise NotFound()
    if not kinds(scope):
        raise PermissionDenied()
    set_rls(
        scope.org.pk,
        user.pk,
        scope_id=scope_of(scope.org.pk),
        todo_department_id=scope.department_id,
    )
    return scope


def _module(scope, kind):
    return AREAS[kind][0] in (scope.org.enabled_modules or [])


def kinds(scope) -> set[str]:
    """Bestandsarten, deren Buchungskalender diese Person sehen darf."""
    result = set()
    for kind, (module, area) in AREAS.items():
        if module not in (scope.org.enabled_modules or []):
            continue
        if {f"{area}.view", "bookings.view"} & scope.permissions:
            result.add(kind)
    return result


def items(scope):
    """Objekte mit Buchungskalender in diesem Datenbereich."""
    from materials.models import MaterialItem

    return MaterialItem.objects.filter(
        organization=scope.org,
        department_id=scope.department_id,
        kind__in=kinds(scope),
        deleted_at__isnull=True,
        booking_rules__enabled=True,
    )


def can_manage(scope, item) -> bool:
    return "bookings.edit" in scope.permissions or (
        f"{AREAS[item.kind][1]}.edit" in scope.permissions and _module(scope, item.kind)
    )


def can_book(scope, item) -> bool:
    if item.condition in ("defective", "retired"):
        return False
    return can_manage(scope, item) or "bookings.view" in scope.permissions


def require_book(scope, item):
    if not can_book(scope, item):
        raise PermissionDenied()


def can_see_details(scope, booking, user) -> bool:
    if can_manage(scope, booking.item) or booking.booked_by_id == user.pk:
        return True
    return booking.visibility != "board"
