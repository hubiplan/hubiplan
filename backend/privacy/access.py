"""Wer die Datenschutz-Werkzeuge sieht und pflegt: ``privacy.view`` und ``privacy.edit``.

Nur Vereine und Dachverbände, nur die Einheit selbst (keine Untereinheiten). Kein
abschaltbares Modul: Das Verzeichnis braucht jeder Verein mit Mitgliederdaten.
"""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

VIEW = "privacy.view"
EDIT = "privacy.edit"


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
    if VIEW not in scope.permissions:
        raise PermissionDenied()
    set_rls(org.pk, user.pk, scope_id=scope_of(org.pk))
    return scope


def require_edit(scope: Scope) -> None:
    if not scope.can_edit:
        raise PermissionDenied()
