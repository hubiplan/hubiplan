"""Wer den Fristenkalender sieht und pflegt: ``obligations.view`` und ``obligations.edit``.

Nur Vereine und Dachverbände, nur die Einheit selbst (keine Untereinheiten).
"""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

MODULE = "obligations"
VIEW = "obligations.view"
EDIT = "obligations.edit"


@dataclass
class Scope:
    org: Organization
    permissions: set[str]

    @property
    def can_edit(self) -> bool:
        return EDIT in self.permissions


def scope_for(user, org_id) -> Scope:
    org = Organization.objects.filter(pk=org_id, type__in=["club", "federation"]).first()
    if org is None:
        raise NotFound()
    scope = Scope(org, set(permissions_in(user, org)))
    if not scope.permissions:
        raise NotFound()
    if MODULE not in (org.enabled_modules or []):
        raise NotFound()
    if VIEW not in scope.permissions:
        raise PermissionDenied()
    set_rls(org.pk, user.pk, scope_id=scope_of(org.pk))
    return scope


def require_edit(scope: Scope) -> None:
    if not scope.can_edit:
        raise PermissionDenied()
