"""Wer Orte sieht und speichert.

Lesen: jede Rolle der Einheit (die Orte erscheinen in vielen Formularen).
Speichern: wer Termine, Wettbewerbe, Helferdienste oder Versammlungen bearbeiten oder die
Einstellungen ändern darf. Untereinheiten speichern in die Orte ihres Vereins; ändern und
löschen kann man Orte nur im Verein bzw. Dachverband selbst.
"""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

EDITORS = frozenset(
    {
        "events.edit",
        "events.manage",
        "dept.events.manage",
        "competitions.edit",
        "competitions.manage",
        "helpers.edit",
        "meetings.edit",
        "settings.edit",
        "org.edit",
    }
)


@dataclass
class Scope:
    org: Organization
    department_id: int | None
    permissions: set[str]

    @property
    def can_edit(self) -> bool:
        return bool(EDITORS & self.permissions)

    @property
    def can_manage(self) -> bool:
        """Ändern und löschen: nur im Verein bzw. Dachverband selbst."""
        return self.department_id is None and self.can_edit


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
    if not scope.permissions:
        raise NotFound()
    set_rls(scope.org.pk, user.pk, scope_id=scope_of(scope.org.pk))
    return scope


def require_edit(scope: Scope) -> None:
    if not scope.can_edit:
        raise PermissionDenied()


def require_manage(scope: Scope) -> None:
    if not scope.can_manage:
        raise PermissionDenied()
