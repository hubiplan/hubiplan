"""Wer Sammelbestellungen in der Verwaltung sieht und bearbeitet (nur im Verein).

Rollenrechte ``orders.view`` und ``orders.edit``; Rechnungen anlegen braucht zusätzlich
``billing.edit`` und das Modul „Beiträge und Rechnungen“.
"""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

MODULE = "orders"
VIEW = "orders.view"
EDIT = "orders.edit"
BILLING = "billing.edit"


@dataclass
class Scope:
    org: Organization
    permissions: set[str]

    @property
    def can_edit(self) -> bool:
        return EDIT in self.permissions

    @property
    def can_invoice(self) -> bool:
        return (
            self.can_edit
            and BILLING in self.permissions
            and "billing" in (self.org.enabled_modules or [])
        )


def scope_for(user, org_id) -> Scope:
    org = Organization.objects.filter(pk=org_id, type="club").first()
    if org is None:
        raise NotFound()
    scope = Scope(org, set(permissions_in(user, org)))
    # Fremde Einheit: immer 404, bevor der Modulzustand etwas verrät
    if not scope.permissions:
        raise NotFound()
    if MODULE not in (org.enabled_modules or []):
        raise NotFound()
    if VIEW not in scope.permissions and EDIT not in scope.permissions:
        raise PermissionDenied()
    set_rls(org.pk, user.pk, scope_id=scope_of(org.pk))
    return scope


def require_edit(scope: Scope) -> None:
    if not scope.can_edit:
        raise PermissionDenied()
