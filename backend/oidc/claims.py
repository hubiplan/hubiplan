"""Wer darf sich bei einem Dienst anmelden, und was erfährt der Dienst über ihn?

Grundlage ist allein die Einheit, die den Dienst eingetragen hat:

- aktive Rollen der Einheit (Vorstand, Kassierer, …) am Benutzerkonto,
- Rollen von Untereinheiten (z. B. Zugführer) über die eigene Mitgliedschaft,
- je nach Einstellung auch der Mitgliederzugang mit laufender Mitgliedschaft.

Rechte höherer Einheiten (z. B. Dachverband) zählen nicht: Wer in die Nextcloud eines
Vereins darf, entscheidet nur der Verein.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from django.db.models import F, Q
from django.utils.translation import gettext

from access.models import RoleAssignment
from core.tenancy import tenant_context
from members.models import DepartmentMembership, DepartmentRoleHolder, today
from portal.models import PortalAccess

from .models import Client

# Gruppennamen in der Nextcloud dürfen höchstens 64 Zeichen haben
GROUP_MAX = 64
# Feste Namen (nicht übersetzt): Die Nextcloud erkennt Gruppen am Namen
BOARD_GROUP = "Vorstand"
MEMBERS_GROUP = "Mitglieder"
# Nie senden: Administratorgruppe der Nextcloud (Gesamtaudit 15.11., AUTH-07/OIDC-1)
NEVER_GROUPS = frozenset({"admin"})


class NotAllowed(Exception):
    """Der Benutzer darf sich bei diesem Dienst nicht anmelden (Text für die Oberfläche)."""


@dataclass
class Profile:
    name: str = ""
    given_name: str = ""
    family_name: str = ""
    email: str = ""
    # Bisheriger Benutzername in der Nextcloud, nur wenn eingetragen
    username: str = ""
    groups: list[str] = field(default_factory=list)


def subject(client: Client, user) -> str:
    """Kennung des Benutzers für genau diesen Dienst (bleibt gleich, solange es ihn gibt)."""
    mac = hmac.new(client.subject_salt.encode(), f"user:{user.pk}".encode(), hashlib.sha256)
    return mac.hexdigest()[:32]


def _group(name: str) -> str:
    return " ".join(str(name or "").split())[:GROUP_MAX]


def _counts(user, assignment) -> bool:
    """Zählt die Rolle? Wie in HUBIplan nur, soweit die Zwei-Faktor-Regel ihre Rechte gewährt.

    Ohne zweiten Faktor ruhen nach Ablauf der Frist alle Verwaltungsrechte (accounts.mfa_policy).
    Die Nextcloud-Anmeldung las die Rollen bisher direkt; ein Vorstand ohne 2FA bekam so weiter
    die Gruppe „Vorstand“ (Gesamtaudit 15.11., AUTH-03). Rollen ohne Rechte zählen wie bisher.
    """
    from accounts.mfa_policy import gate

    perms = set(assignment.role.permissions or [])
    return not perms or bool(gate(user, perms))


def profile(client: Client, user) -> Profile:
    """Angaben für den Dienst; ``NotAllowed``, wenn der Benutzer nicht hinein darf."""
    org = client.organization
    if not user.is_active or not org.is_active or not client.is_active:
        raise NotAllowed(gettext("Die Anmeldung bei diesem Dienst ist nicht möglich."))
    on = today()
    with tenant_context(org.pk, user.pk):
        roles = list(
            RoleAssignment.objects.filter(user=user, organization=org)
            .active(on)
            .select_related("role", "person")
        )
        # Eigener Zugang vor dem Zugang als Ansprechpartner einer Organisation (J5)
        access = (
            PortalAccess.objects.filter(user=user, organization=org)
            .select_related("membership__person", "contact_person__person")
            .order_by(F("contact_person").asc(nulls_first=True), "pk")
            .first()
        )
        membership = access.membership if access else None
        if membership is not None and membership.current_period(on) is None:
            membership = None
        units: list = []
        unit_roles: list = []
        if membership is not None:
            units = [
                dm.department
                for dm in DepartmentMembership.objects.filter(
                    membership=membership, valid_from__lte=on, department__is_active=True
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
                .select_related("department")
            ]
            unit_roles = list(
                DepartmentRoleHolder.objects.filter(
                    membership=membership, role__department__is_active=True
                )
                .active(on)
                .select_related("role__department")
            )

    roles = [a for a in roles if _counts(user, a)]
    unit_roles = [h for h in unit_roles if _counts(user, h)]
    is_member = membership is not None
    if client.audience == Client.Audience.ROLES:
        # Nur Rollen dieser Einheit: Ämter in Untereinheiten zählen nicht, auch nicht als Gruppe
        unit_roles = []
    allowed = bool(roles) or bool(unit_roles)
    if client.audience == Client.Audience.MEMBERS:
        allowed = allowed or is_member
    if not allowed:
        raise NotAllowed(
            gettext("Dein Konto hat bei {org} keinen Zugang zu „{name}“.").format(
                org=org.name, name=client.name
            )
        )

    groups: list[str] = []
    if client.groups_board and any(a.role.is_board for a in roles):
        groups.append(BOARD_GROUP)
    # Frei benannte Gruppen (Rollen- und Einheitsnamen) dürfen keine feste Gruppe ergeben: Eine
    # Untereinheit „Vorstand“ gäbe sonst allen ihren Mitgliedern die Vorstandsgruppe, eine Rolle
    # „admin“ die Administratorgruppe der Nextcloud (Gesamtaudit 15.11., OIDC-1). Solche Namen
    # entfallen; bestehende Gruppen werden nicht umbenannt.
    reserved = {_group(g).casefold() for g in (BOARD_GROUP, MEMBERS_GROUP, client.account_group)}
    reserved |= set(NEVER_GROUPS)
    reserved.discard("")

    def free(name: str) -> None:
        if _group(name).casefold() not in reserved:
            groups.append(name)

    # Zugeordnete Gruppen gehen immer mit; Rollen ohne Zuordnung nur mit „je Rolle eine Gruppe“.
    # Vereinsrollen (access.Role) und Abteilungsämter (organizations.DepartmentRole) stammen aus
    # verschiedenen Tabellen mit eigenen Nummernkreisen: role_groups gilt nur für Vereinsrollen.
    for a in roles:
        mapped = client.groups_for_role(a.role_id)
        if mapped:
            groups += mapped
        elif client.groups_roles:
            free(a.role.name)
    if client.groups_roles:
        for h in unit_roles:
            free(f"{h.role.name} ({h.role.department.name})")
    if client.groups_units:
        for u in units:
            free(u.name)
    if client.groups_members and is_member:
        groups.append(MEMBERS_GROUP)
    # Gruppe aller Konten über HUBIplan: Ihr Gruppen-Admin (Dienstkonto) kann sie deaktivieren
    if client.account_group:
        groups.append(client.account_group)
    seen: set[str] = set()
    unique = []
    for g in map(_group, groups):
        # Die Administratorgruppe nie, auch nicht über eine Zuordnung (AUTH-07)
        if g and g not in seen and g.casefold() not in NEVER_GROUPS:
            seen.add(g)
            unique.append(g)

    person = membership.person if membership is not None else None
    contact_names = None
    if access is not None and access.contact_person_id is not None:
        # Ansprechpartner: eigener Name, nicht der Name der Organisation
        from portal.services import contact_names as names_of

        person = None
        with tenant_context(org.pk, user.pk):
            contact_names = names_of(access.contact_person)
    if person is None and contact_names is None:
        person = next((a.person for a in roles if a.person_id), None)
    if contact_names is not None:
        given, family = (n.strip() for n in contact_names)
    else:
        given = (getattr(person, "first_name", "") or user.first_name or "").strip()
        family = (getattr(person, "last_name", "") or user.last_name or "").strip()
    name = " ".join(p for p in (given, family) if p) or user.email.split("@")[0]
    return Profile(
        name=name,
        given_name=given,
        family_name=family,
        email=user.email,
        username=client.username_map().get(user.email.lower(), ""),
        groups=unique,
    )
