"""Einstellungen › Konten: alle Konten der Einheit mit Rollen, Mitgliederbereich und Anmeldung.

Rollen-Vorschlag R4 (konzepte/rollen-zugaenge.md). Konten mit Rollen der Einheit
(Vorstandskonten) sieht nur, wer Rollen lesen darf; Konten nur für den Mitgliederbereich
sieht, wer die Konten der Mitglieder lesen darf. Sammelaktion: Anmeldelink erneut senden.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mfa_policy import has_mfa
from accounts.tokens import INVITATION_DAYS, is_invitation
from audit.log import record
from core.api_base import OrgScopedMixin, has_needed

from .catalog import LOGINS_EDIT, LOGINS_VIEW, ROLES_EDIT, ROLES_MANAGE, ROLES_VIEW
from .models import RoleAssignment

ROLES_WRITE = (ROLES_MANAGE, ROLES_EDIT)
MAX_RESEND = 200


def _name(person) -> str:
    return f"{person.first_name} {person.last_name}".strip()


def collect(org, perms: set[str]) -> dict[int, dict]:
    """Konten der Einheit, je Konto eine Zeile (intern mit Rolle und Zugang)."""
    from members.models import Membership
    from portal.models import PortalAccess

    rows: dict[int, dict] = {}

    def row(user) -> dict:
        if user.pk not in rows:
            rows[user.pk] = {
                "user": user,
                "name": user.get_full_name(),
                "membership": None,
                "roles": [],
                "rights": False,
                "assignment": None,
                "access": None,
            }
        return rows[user.pk]

    if has_needed(perms, ROLES_VIEW):
        assignments = (
            RoleAssignment.objects.filter(organization=org, user__isnull=False, name="")
            .active()
            .select_related("user", "role", "person")
            .order_by("valid_from")
        )
        for a in assignments:
            r = row(a.user)
            r["roles"].append(a.role.name)
            r["rights"] = r["rights"] or bool(a.role.permissions)
            r["assignment"] = r["assignment"] or a
            if a.person_id:
                r["name"] = _name(a.person)
                membership = (
                    Membership.objects.filter(organization=org, person_id=a.person_id)
                    .order_by("-pk")
                    .values_list("pk", flat=True)
                    .first()
                )
                r["membership"] = r["membership"] or membership
    if has_needed(perms, LOGINS_VIEW):
        accesses = PortalAccess.objects.filter(organization=org).select_related(
            "user", "membership__person"
        )
        for access in accesses:
            if access.user_id not in rows and has_board_role(org, access.user_id, perms):
                continue
            r = row(access.user)
            r["access"] = access
            r["membership"] = access.membership_id
            r["name"] = _name(access.membership.person)
    return rows


def has_board_role(org, user_id: int, perms: set[str]) -> bool:
    """Konto hat eine Rolle der Einheit, aber hier fehlt das Recht, Rollen zu lesen."""
    if has_needed(perms, ROLES_VIEW):
        return False
    return RoleAssignment.objects.filter(organization=org, user_id=user_id).active().exists()


def account_data(r: dict) -> dict:
    user = r["user"]
    awaiting = is_invitation(user)
    old = timezone.now() - datetime.timedelta(days=INVITATION_DAYS)
    mfa = has_mfa(user)
    return {
        "id": user.pk,
        "name": r["name"] or user.email,
        "email": user.email,
        "membership": r["membership"],
        "roles": r["roles"],
        "rights": r["rights"],
        "member_area": r["access"] is not None,
        "last_login": user.last_login,
        "awaiting_password": awaiting,
        "invitation_expired": awaiting and user.date_joined < old,
        "has_mfa": mfa,
        "mfa_missing": not mfa and user.mfa_required_by is not None,
    }


class AccountsView(OrgScopedMixin, APIView):
    """GET: alle Konten der Einheit."""

    read_permission = (LOGINS_VIEW, ROLES_VIEW)

    def get(self, request, org_id: int):
        rows = collect(self.org, self.org_permissions)
        data = [account_data(r) for r in rows.values()]
        data.sort(key=lambda d: (d["name"].lower(), d["email"]))
        return Response(data)


class ResendSerializer(serializers.Serializer):
    users = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, max_length=MAX_RESEND
    )


class AccountsResendView(OrgScopedMixin, APIView):
    """POST: Anmeldelink bzw. Einladung an die gewählten Konten erneut senden."""

    write_permission = (LOGINS_EDIT, *ROLES_WRITE)

    @transaction.atomic
    def post(self, request, org_id: int):
        from accounts.invitations import send_invitation
        from portal.services import send_access_mail

        data = ResendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        perms = self.org_permissions
        rows = collect(self.org, perms)
        sent, skipped = [], []
        for user_id in dict.fromkeys(data.validated_data["users"]):
            r = rows.get(user_id)
            if r is None:
                raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
            user = r["user"]
            if r["assignment"] is not None:
                # Konto mit Rolle: nur die Einladung, solange kein Passwort festgelegt ist
                if not has_needed(perms, ROLES_WRITE) or not is_invitation(user):
                    skipped.append(user.email)
                    continue
                ok = send_invitation(user, self.org, r["assignment"].role.name)
                target = r["assignment"]
            elif r["access"] is not None:
                if not has_needed(perms, LOGINS_EDIT):
                    skipped.append(user.email)
                    continue
                send_access_mail(self.org, r["access"], request.user)
                ok = True
                target = r["access"].membership
            else:
                skipped.append(user.email)
                continue
            if not ok:
                skipped.append(user.email)
                continue
            record(
                self.org,
                request.user,
                "update",
                target,
                {"Anmeldelink": [None, f"erneut an {user.email} gesendet"]},
                person=getattr(target, "person", None),
            )
            sent.append(user.email)
        return Response({"sent": sent, "skipped": skipped})
