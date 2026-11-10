"""Wer darf was in welcher Organisation?"""

from __future__ import annotations

from organizations.models import Organization

from .catalog import (
    BILLING_EDIT,
    BILLING_VIEW,
    FINANCE_EDIT,
    FINANCE_VIEW,
    ROLES_EDIT,
    ROLES_MANAGE,
    codes_for,
    effective,
    enabled_codes_for,
)
from .models import RoleAssignment


def permissions_in(user, org: Organization) -> set[str]:
    """Berechtigungen eines Benutzers in einer Organisation (aus aktiven Rollen).

    Während einer Ansicht als Rolle (access/preview.py) gilt in deren Einheit nur die
    Schnittmenge aus den eigenen Rechten und denen der Rolle.
    """
    from . import preview

    return preview.apply(user, org, own_permissions_in(user, org))


def own_permissions_in(user, org: Organization) -> set[str]:
    """Eigene Berechtigungen, ohne Ansicht als Rolle.

    Superuser (Betreiber der Instanz) haben auf der Plattform alle Rechte. Auf
    Vereins- und Dachverbandsebene gelten auch für sie nur zugewiesene Rollen.
    """
    if not user.is_authenticated or not org.is_active and org.type != Organization.Type.PLATFORM:
        return set()
    if org.is_remote:
        return set()  # Platzhalter einer Einheit auf einer anderen Instanz: hier arbeitet niemand
    from accounts.mfa_policy import gate

    platform = org.type == Organization.Type.PLATFORM
    if user.is_superuser and platform:
        return gate(user, allowed_codes(org.type), platform=True)
    if org.type == Organization.Type.UNIT and not _workspace_open(org):
        return set()
    perms = _assigned(user, org)
    if org.type == Organization.Type.UNIT:
        perms |= inherited_permissions(user, org)
    return gate(user, perms & effective(enabled_codes_for(org)), platform=platform)


def allowed_codes(org_type: str) -> set[str]:
    """Codes einer Einheitenart, neu und (für den Übergang) in der früheren Form."""
    return effective(codes_for(org_type))


def _assigned(user, org: Organization) -> set[str]:
    perms: set[str] = set()
    assignments = RoleAssignment.objects.active().filter(user=user, organization=org)
    for assignment in assignments.select_related("role"):
        perms.update(assignment.role.permissions or [])
    return effective(perms)


def role_focus(codes) -> set[str]:
    """Schwerpunkt einer Rolle für die Startseite (S-04): ``finance`` (Kasse), ``minutes``
    (Schriftführung). Eine Rolle, die Rollen vergeben darf (Vorsitz, Vollrechte), hat keinen
    Schwerpunkt: Kassenrechte allein machen niemanden zur Kasse."""
    perms = effective(codes or [])
    if ROLES_EDIT in perms or ROLES_MANAGE in perms:
        return set()
    out: set[str] = set()
    if FINANCE_EDIT in perms or BILLING_EDIT in perms:
        out.add("finance")
    if "meetings.edit" in perms:
        out.add("minutes")
    return out


def home_focus(user, org: Organization, preview_codes=None) -> list[str]:
    """Schwerpunkte aus den einzelnen Rollen der Person (bei Ansicht als Rolle aus dieser)."""
    if preview_codes is not None:
        return sorted(role_focus(preview_codes))
    out: set[str] = set()
    assignments = RoleAssignment.objects.active().filter(user=user, organization=org)
    for assignment in assignments.select_related("role"):
        out |= role_focus(assignment.role.permissions)
    return sorted(out)


def _workspace_open(unit: Organization) -> bool:
    """Arbeitsbereich einer Untereinheit: eingeschaltet und die Einheit darüber aktiv."""
    return bool(unit.own_workspace and unit.organization and unit.organization.is_active)


def inherited_permissions(user, unit: Organization) -> set[str]:
    """Rechte aus den Einheiten darüber im Arbeitsbereich einer Untereinheit.

    Wer darüber Rollen verwaltet, richtet auch die Rollen der Untereinheit ein; wer
    darüber die Kasse sieht oder führt, sieht die Kasse der Untereinheit (nur lesen),
    ebenso die Rechnungen.
    """
    above: set[str] = set()
    for node in unit.ancestors()[1:]:
        # Eine stillgelegte Einheit darüber vermittelt keine Rechte mehr (AT-V01)
        if not node.is_active:
            break
        if node.type == Organization.Type.UNIT and not node.own_workspace:
            continue
        above |= _assigned(user, node) & effective(enabled_codes_for(node))
        if node.type != Organization.Type.UNIT:
            break
    result: set[str] = set()
    if above & {ROLES_MANAGE, ROLES_EDIT}:
        result.add(ROLES_EDIT)
    if above & {FINANCE_VIEW, FINANCE_EDIT}:
        result.add(FINANCE_VIEW)
    if above & {BILLING_VIEW, BILLING_EDIT}:
        result.add(BILLING_VIEW)
    return effective(result)


def is_platform_admin(user) -> bool:
    from core.tenancy import user_view

    from .catalog import PLATFORM_MANAGE

    # Auch für ein noch nicht angemeldetes Konto (Verbundanmeldung) verlässlich (AT-S01)
    with user_view(user.pk):
        return PLATFORM_MANAGE in permissions_in(user, Organization.platform())


def platform_rights_waiting(user) -> bool:
    """Hätte das Konto Rechte der Plattform-Verwaltung, die ohne zweiten Faktor ruhen?"""
    if not getattr(user, "pk", None):
        return False
    if user.is_superuser:
        return True
    from core.tenancy import user_view

    platform = Organization.platform()
    with user_view(user.pk):
        return bool(_assigned(user, platform) & effective(enabled_codes_for(platform)))


def organizations_for(user) -> list[tuple[Organization, set[str]]]:
    """Alle Organisationen, in denen der Benutzer gerade eine Rolle hat."""
    if not user.is_authenticated:
        return []
    org_ids = set(
        RoleAssignment.objects.active().filter(user=user).values_list("organization_id", flat=True)
    )
    if user.is_superuser:
        org_ids.add(Organization.platform().pk)
    # Arbeitsbereiche von Untereinheiten, in die Rechte von oben reichen
    areas = org_ids | set(
        Organization.objects.filter(pk__in=org_ids, type=Organization.Type.UNIT).values_list(
            "organization_id", flat=True
        )
    )
    org_ids |= set(
        Organization.objects.filter(
            type=Organization.Type.UNIT, own_workspace=True, organization_id__in=areas
        ).values_list("pk", flat=True)
    )
    orgs = Organization.objects.filter(pk__in=org_ids, is_active=True).select_related(
        "parent", "parent__parent", "organization"
    )
    result = []
    for org in orgs:
        perms = permissions_in(user, org)
        if perms or org.type != Organization.Type.UNIT:
            result.append((org, perms))
    order = {
        Organization.Type.PLATFORM: 0,
        Organization.Type.FEDERATION: 1,
        Organization.Type.CLUB: 2,
        Organization.Type.UNIT: 3,
    }
    result.sort(key=lambda item: (order.get(item[0].type, 9), item[0].name))
    return result
