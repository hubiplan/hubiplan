"""Wer Helferdienste sieht und bearbeitet (konzepte/helferdienste.md, Abschnitt 4).

Verein oder Dachverband: Rollenrechte ``helpers.view`` und ``helpers.edit``.
Untereinheit (z. B. Zug): dieselben Codes aus den Rollen der Untereinheit.
"""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

MODULE = "helpers"
VIEW = "helpers.view"
EDIT = "helpers.edit"


@dataclass
class Scope:
    org: Organization
    department_id: int | None
    permissions: set[str]

    @property
    def can_edit(self) -> bool:
        return EDIT in self.permissions


def scope_for(user, org_id=None, dept_id=None) -> Scope:
    if dept_id is not None:
        from portal.services import department_contexts

        ctx = department_contexts(user).get(int(dept_id))
        if ctx is None:
            raise NotFound()
        scope = Scope(ctx.club, ctx.department.pk, set(ctx.permissions))
    else:
        org = Organization.objects.filter(pk=org_id, type__in=["club", "federation"]).first()
        if org is None:
            raise NotFound()
        scope = Scope(org, None, set(permissions_in(user, org)))
    if MODULE not in (scope.org.enabled_modules or []):
        raise NotFound()
    if VIEW not in scope.permissions:
        raise PermissionDenied()
    set_rls(scope.org.pk, user.pk, scope_id=scope_of(scope.org.pk))
    return scope


def require_edit(scope: Scope) -> None:
    if not scope.can_edit:
        raise PermissionDenied()
