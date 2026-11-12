"""API für Zugänge: Mitgliederbereich, Abteilungsbereich, Anmeldelinks.

Drei Bereiche:

- ``/api/orgs/<id>/…``: der Vereinsvorstand richtet Zugänge ein und bearbeitet
  Datenänderungen.
- ``/api/depts/<id>/…``: Abteilungsrollen arbeiten mit den Mitgliedern ihrer
  Abteilung. Die Datenbank arbeitet dabei im Kontext des Vereins (RLS); die
  Anwendung begrenzt zusätzlich auf die Abteilung.
- ``/api/portal/…``: das Mitglied sieht seine eigenen Daten.
"""

from __future__ import annotations

from django.contrib.auth import login
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext, gettext_noop
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    DEPT_ACCESS_MANAGE,
    DEPT_MEMBERS_EDIT,
    DEPT_MEMBERS_VIEW,
    DEPT_ROLES_MANAGE,
    LOGINS_EDIT,
    LOGINS_VIEW,
    ROLES_VIEW,
    catalog_for,
    effective,
)
from access.modules import MODULE_IDS, module_on
from accounts.models import User
from audit.log import diff, record, snapshot
from core.api_base import has_needed
from core.ratelimit import client_ip, too_many
from core.tenancy import scope_of, set_rls, tenant_context
from members import services as member_services
from members.models import (
    DepartmentMembership,
    DepartmentRoleHolder,
    Gender,
    Membership,
    today,
)
from members.personsearch import ordered
from members.serializers import MemberUpdateSerializer, TitleField
from members.views import (
    MemberPagination,
    _ClubMixin,
    filter_members,
    member_queryset,
    member_rows,
    update_member,
)
from organizations.imprint import ensure as ensure_imprint
from organizations.models import DepartmentRole
from organizations.serializers import clean_department_permissions
from organizations.terms import department_terms, fill
from organizations.theme import effective_theme
from organizations.tree import UnitTree, subtree_ids

from . import cancellation, services
from .models import CancellationRequest, ChangeRequest, LoginLink, PortalAccess, hash_token

# --- Vereinsseite: Zugänge und Datenänderungen ---


class MemberAccessView(_ClubMixin, APIView):
    """Zugang eines Mitglieds: ansehen, einrichten/Link senden, entfernen."""

    # Bereich „Zugänge der Mitglieder“ (früher: Mitglieder lesen bzw. bearbeiten)
    read_permission = LOGINS_VIEW
    write_permission = LOGINS_EDIT

    def get_membership(self) -> Membership:
        return get_object_or_404(
            Membership.objects.select_related("person"), organization=self.org, pk=self.kwargs["pk"]
        )

    def get_contact(self, membership):
        """Ansprechpartner (``?ansprechpartner=<id>``): Zugang für ihn statt für das Mitglied
        (Organisationsmitglieder, J5)."""
        from members.models import ContactPerson

        raw = self.request.query_params.get("ansprechpartner") or self.request.data.get("contact")
        if not raw:
            return None
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"contact": "?"}) from None
        return get_object_or_404(
            ContactPerson.objects.select_related("person"), membership=membership, pk=pk
        )

    def current(self, membership, contact):
        return (
            PortalAccess.objects.filter(membership=membership, contact_person=contact)
            .select_related("user")
            .first()
        )

    def get(self, request, org_id: int, pk: int):
        membership = self.get_membership()
        access = self.current(membership, self.get_contact(membership))
        return Response(
            {
                "access": services.access_info(access),
                "portal_enabled": self.org.member_portal_enabled,
                "department_access_enabled": self.org.department_access_enabled,
            }
        )

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        membership = self.get_membership()
        if not (self.org.member_portal_enabled or self.org.department_access_enabled):
            raise serializers.ValidationError(
                fill(
                    "Bitte zuerst unter Einstellungen → Organisation den Mitgliederbereich "
                    "oder den Zugang für {pl} freischalten.",
                    self.org,
                )
            )
        contact = self.get_contact(membership)
        before = self.current(membership, contact)
        old_email = before.user.email if before else None
        transfer = bool(request.data.get("transfer"))
        access = services.ensure_access(
            self.org, membership, request.user, transfer=transfer, contact=contact
        )
        kind = services.send_access_mail(self.org, access, request.user)
        if old_email and old_email != access.user.email:
            record(
                self.org,
                request.user,
                "update",
                membership,
                {"Zugang übertragen": [old_email, access.user.email]},
                person=membership.person,
            )
        record(
            self.org,
            request.user,
            "update",
            membership,
            {
                "Zugang": [
                    None,
                    f"{'Anmeldelink' if kind == 'link' else 'Passwort-Link'} an "
                    f"{access.user.email} gesendet",
                ]
            },
            person=membership.person,
        )
        return Response({"access": services.access_info(access), "sent": kind})

    def delete(self, request, org_id: int, pk: int):
        membership = self.get_membership()
        contact = self.get_contact(membership)
        access = self.current(membership, contact)
        if contact is not None and contact.member_access:
            contact.member_access = False
            contact.save(update_fields=["member_access", "updated_at"])
        if access is not None:
            email = access.user.email
            access.delete()
            record(
                self.org,
                request.user,
                "update",
                membership,
                {"Zugang": [email, None]},
                person=membership.person,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


def change_request_data(cr: ChangeRequest) -> dict:
    person = cr.membership.person
    return {
        "id": cr.pk,
        "member_id": cr.membership_id,
        "member_name": f"{person.first_name} {person.last_name}",
        "data": cr.data,
        "previous": cr.previous,
        "message": cr.message,
        "status": cr.status,
        "status_label": cr.get_status_display(),
        "response": cr.response,
        "created_at": cr.created_at,
        "decided_at": cr.decided_at,
    }


class ChangeRequestListView(_ClubMixin, APIView):
    def get(self, request, org_id: int):
        qs = ChangeRequest.objects.filter(organization=self.org).select_related(
            "membership__person"
        )
        wanted = request.query_params.get("status", "pending")
        if wanted != "alle":
            qs = qs.filter(status=wanted)
        return Response([change_request_data(cr) for cr in qs[:200]])


class DecisionSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    response = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # Felder, die seit der Meldung im Verein geändert wurden, trotzdem überschreiben
    overwrite = serializers.BooleanField(required=False, default=False)


def current_values(club, membership) -> dict:
    """Heutige Werte der Felder, die ein Mitglied selbst melden kann."""
    current = dept_member_detail(club, membership, with_access=False)
    return {
        "last_name": current["last_name"],
        "first_name": current["first_name"],
        "birth_date": current["birth_date"].isoformat() if current["birth_date"] else None,
        "gender": current["gender"],
        "title": current.get("title", ""),
        **(current["contact"] or {}),
    }


FIELD_LABELS = {
    "last_name": "Nachname",
    "first_name": "Vorname",
    "birth_date": "Geburtsdatum",
    "gender": "Geschlecht",
    "title": "Titel",
    "email": "E-Mail",
    "phone": "Telefon",
    "mobile": "Mobil",
    "street": "Straße",
    "postal_code": "PLZ",
    "city": "Ort",
    "country": "Land",
}


def conflicts(club, cr: ChangeRequest) -> list[str]:
    """Felder der Meldung, die der Verein inzwischen anders geändert hat."""
    now = current_values(club, cr.membership)
    return [
        key
        for key, wanted in (cr.data or {}).items()
        if key in (cr.previous or {})
        and (now.get(key) or "") != (cr.previous.get(key) or "")
        and (now.get(key) or "") != (wanted or "")
    ]


def _sync_login_email(cr: ChangeRequest) -> None:
    """Neue E-Mail aus einer angenommenen Meldung auch als Anmelde-E-Mail anbieten.

    Die Freigabe des Vereins ändert das Konto nicht selbst: Das Mitglied bekommt
    einen Bestätigungslink an die neue Adresse, wie beim Ändern im eigenen Konto;
    erst danach gilt sie, und alte Anmeldelinks werden ungültig (Audit ID-N01)."""
    from accounts.models import User
    from accounts.self_service import request_email_change

    new = (cr.data or {}).get("email")
    if not new:
        return
    access = (
        PortalAccess.objects.filter(membership=cr.membership, contact_person__isnull=True)
        .select_related("user")
        .first()
    )
    # Nur für das Konto, das die Meldung geschickt hat (Zugang inzwischen neu vergeben?)
    if access is None or access.user_id != cr.user_id:
        return
    if access.user.email.lower() == new.lower():
        return
    if User.objects.filter(email__iexact=new).exclude(pk=access.user_id).exists():
        return
    request_email_change(
        access.user,
        User.objects.normalize_email(new).lower(),
        org_name=cr.membership.organization.name,
    )


class ChangeRequestDecisionView(_ClubMixin, APIView):
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        cr = get_object_or_404(
            ChangeRequest.objects.select_related("membership__person").select_for_update(
                of=("self",)
            ),
            organization=self.org,
            pk=pk,
        )
        if cr.status != ChangeRequest.Status.PENDING:
            raise serializers.ValidationError(gettext("Diese Meldung ist schon bearbeitet."))
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["accept"]:
            changed = conflicts(self.org, cr)
            if changed and not data.validated_data["overwrite"]:
                # Nicht still überschreiben, was der Verein seit der Meldung geändert hat
                names = ", ".join(FIELD_LABELS.get(k, k) for k in changed)
                return Response(
                    {
                        "detail": gettext(
                            "Seit der Meldung wurde im Verein geändert: {names}. Annehmen "
                            "überschreibt diese Angaben mit der Meldung."
                        ).format(names=names),
                        "conflicts": changed,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            values = MemberUpdateSerializer(data=cr.data, partial=True)
            values.is_valid(raise_exception=True)
            update_member(self.org, cr.membership, values.validated_data, request.user)
            _sync_login_email(cr)
            cr.status = ChangeRequest.Status.ACCEPTED
        else:
            cr.status = ChangeRequest.Status.REJECTED
        cr.response = data.validated_data.get("response", "")
        cr.decided_by = request.user
        cr.decided_at = timezone.now()
        cr.save()
        from devices.push import notify_membership

        accepted = cr.status == ChangeRequest.Status.ACCEPTED
        notify_membership(
            cr.membership_id,
            gettext_noop("Deine Änderung wurde übernommen")
            if accepted
            else gettext_noop("Deine Änderung wurde abgelehnt"),
            cr.response or self.org.name,
        )
        return Response(change_request_data(cr))


class CancellationListView(_ClubMixin, APIView):
    """Kündigungen der Mitglieder aus dem Mitgliederbereich."""

    def get(self, request, org_id: int):
        qs = CancellationRequest.objects.filter(organization=self.org).select_related(
            "membership__person"
        )
        wanted = request.query_params.get("status", "pending")
        if wanted != "alle":
            qs = qs.filter(status=wanted)
        return Response([cancellation.request_data(c) for c in qs[:200]])


class CancellationDecisionSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    response = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # Der Verein darf das Austrittsdatum beim Bestätigen anpassen (z. B. nach Satzung)
    exit_date = serializers.DateField(required=False, allow_null=True)


class CancellationDecisionView(_ClubMixin, APIView):
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        c = get_object_or_404(
            CancellationRequest.objects.select_related("membership__person").select_for_update(
                of=("self",)
            ),
            organization=self.org,
            pk=pk,
        )
        data = CancellationDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        cancellation.decide(
            self.org,
            c,
            request.user,
            accept=v["accept"],
            response=v.get("response", ""),
            exit_date=v.get("exit_date"),
        )
        return Response(cancellation.request_data(c))


# --- Abteilungsbereich ---


class DepartmentScopedMixin:
    """API-Ansicht in einer Abteilung (URL-Parameter ``dept_id``)."""

    read_permission: str | None = DEPT_MEMBERS_VIEW
    write_permission: str | None = DEPT_MEMBERS_EDIT

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ctx = services.department_contexts(request.user).get(int(kwargs["dept_id"]))
        if ctx is None:
            raise NotFound()
        needed = (
            self.read_permission
            if request.method in ("GET", "HEAD", "OPTIONS")
            else self.write_permission
        )
        if not has_needed(ctx.permissions, needed):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        self.ctx = ctx
        self.dept = ctx.department
        self.org = ctx.club
        self.dept_permissions = ctx.permissions
        set_rls(self.org.pk, request.user.pk, scope_id=scope_of(self.org.pk))

    def dept_members(self):
        on = today()
        in_dept = DepartmentMembership.objects.filter(
            membership=OuterRef("pk"), department_id__in=subtree_ids(self.dept), valid_from__lte=on
        ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
        return member_queryset(self.org).filter(Exists(in_dept), is_current=True)

    def get_member(self, pk: int) -> Membership:
        membership = self.dept_members().filter(pk=pk).select_related("person").first()
        if membership is None:
            raise NotFound()
        return membership


def department_summary(ctx: services.DepartmentContext) -> dict:
    club = ctx.club
    return {
        "id": ctx.department.pk,
        "name": ctx.department.name,
        "display_name": ctx.department.display_name,
        "club_id": club.pk,
        "club_name": club.name,
        "club_display_name": club.display_name,
        # Bezeichnung dieser Einheit: Vorgabe der direkt übergeordneten Einheit
        "label": ctx.department.parent.department_label,
        "terms": department_terms(ctx.department.parent),
        "path": UnitTree.of(club.pk).path(ctx.department.pk),
        "date_precision": ctx.department.effective_date_precision,
        "permissions": sorted(ctx.permissions),
        "theme": effective_theme(ctx.department.ancestors()),
        "events_enabled": "events" in (club.enabled_modules or []),
        "material_enabled": "material" in (club.enabled_modules or []),
        "infrastructure_enabled": "infrastructure" in (club.enabled_modules or []),
        "meetings_enabled": "meetings" in (club.enabled_modules or []),
        "helpers_enabled": "helpers" in (club.enabled_modules or []),
        "bookings_enabled": "bookings" in (club.enabled_modules or []),
        # Für diese Untereinheit wirksame Module (Teilmenge des Vereins, eigene Kasse usw.)
        "modules": [m for m in MODULE_IDS if module_on(ctx.department, m)],
        "imprint_key": ensure_imprint(ctx.department).public_key,
    }


class DepartmentInfoView(DepartmentScopedMixin, APIView):
    read_permission = None

    def get(self, request, dept_id: int):
        return Response(department_summary(self.ctx))


class DepartmentMemberListView(DepartmentScopedMixin, APIView):
    def get(self, request, dept_id: int):
        params = request.query_params.copy()
        params["status"] = "alle"  # schon auf aktuelle Mitglieder begrenzt
        qs = filter_members(self.dept_members(), params, self.org, lazy=True)
        paginator = MemberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(member_rows(page, self.org))


def dept_member_detail(org, membership: Membership, with_access: bool) -> dict:
    person = membership.person
    contact = member_services.contact_for(person, org)
    current_type = membership.current_type()
    on = today()
    departments = (
        DepartmentMembership.objects.filter(membership=membership, valid_from__lte=on)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
        .select_related("department")
    )
    first = membership.periods.order_by("entry_date").first()
    data = {
        "id": membership.pk,
        "kind": person.kind,
        "display_name": person.display_name,
        "last_name": person.last_name,
        "first_name": person.first_name,
        "birth_date": person.birth_date,
        "gender": person.gender,
        "title": person.title,
        "club_number": membership.club_number,
        "member_type": current_type.member_type.name if current_type else None,
        "entry_date": first.entry_date if first else None,
        "departments": [d.department.display_name for d in departments],
        "contact": (
            {f: getattr(contact, f) for f in member_services.CONTACT_FIELDS} if contact else None
        ),
    }
    if with_access:
        access = (
            PortalAccess.objects.filter(membership=membership, contact_person__isnull=True)
            .select_related("user")
            .first()
        )
        data["access"] = services.access_info(access)
    return data


class DepartmentMemberDetailView(DepartmentScopedMixin, APIView):
    def get(self, request, dept_id: int, pk: int):
        membership = self.get_member(pk)
        return Response(
            dept_member_detail(self.org, membership, LOGINS_VIEW in self.dept_permissions)
        )

    @transaction.atomic
    def patch(self, request, dept_id: int, pk: int):
        membership = self.get_member(pk)
        data = MemberUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        values.pop("club_number", None)  # Vereinsnummer vergibt der Verein
        update_member(self.org, membership, values, request.user)
        return Response(
            dept_member_detail(self.org, membership, LOGINS_VIEW in self.dept_permissions)
        )


class DepartmentMemberAccessView(DepartmentScopedMixin, APIView):
    read_permission = LOGINS_VIEW
    write_permission = DEPT_ACCESS_MANAGE

    @transaction.atomic
    def post(self, request, dept_id: int, pk: int):
        membership = self.get_member(pk)
        before = (
            PortalAccess.objects.filter(membership=membership, contact_person__isnull=True)
            .select_related("user")
            .first()
        )
        old_email = before.user.email if before else None
        transfer = bool(request.data.get("transfer"))
        access = services.ensure_access(self.org, membership, request.user, transfer=transfer)
        kind = services.send_access_mail(self.org, access, request.user)
        changes = {"Zugang": [None, f"Link an {access.user.email} gesendet ({self.dept.name})"]}
        if old_email and old_email != access.user.email:
            changes["Zugang übertragen"] = [old_email, access.user.email]
        record(self.org, request.user, "update", membership, changes, person=membership.person)
        return Response({"access": services.access_info(access), "sent": kind})

    def delete(self, request, dept_id: int, pk: int):
        membership = self.get_member(pk)
        PortalAccess.objects.filter(membership=membership, contact_person__isnull=True).delete()
        record(
            self.org,
            request.user,
            "update",
            membership,
            {"Zugang": ["vorhanden", None]},
            person=membership.person,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeptRoleSerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    holder_count = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentRole
        fields = ["id", "name", "permissions", "holder_count"]

    def get_holder_count(self, obj) -> int:
        on = today()
        return (
            obj.holders.filter(valid_from__lte=on)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
            .count()
        )

    def validate_permissions(self, value):
        return clean_department_permissions(
            value,
            org=self.context["dept"].organization,
            stored=self.instance.permissions if self.instance else [],
        )

    def validate_name(self, value):
        dept = self.context["dept"]
        qs = DepartmentRole.objects.filter(department=dept, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(gettext("Diese Rolle gibt es schon."))
        return value


class DepartmentRolesView(DepartmentScopedMixin, APIView):
    read_permission = ROLES_VIEW
    write_permission = DEPT_ROLES_MANAGE

    def get(self, request, dept_id: int):
        roles = DepartmentRole.objects.filter(department=self.dept)
        return Response(
            {
                "roles": DeptRoleSerializer(roles, many=True).data,
                "catalog": catalog_for("department", self.org),
            }
        )

    def post(self, request, dept_id: int):
        data = DeptRoleSerializer(data=request.data, context={"dept": self.dept})
        data.is_valid(raise_exception=True)
        role = data.save(department=self.dept, organization=self.org)
        record(self.org, request.user, "create", role, diff({}, snapshot(role)))
        return Response(DeptRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class DepartmentRoleOrderView(DepartmentScopedMixin, APIView):
    """POST: Reihenfolge der Rollen der Untereinheit (per Ziehen)."""

    read_permission = ROLES_VIEW
    write_permission = DEPT_ROLES_MANAGE

    def post(self, request, dept_id: int):
        from core.reorder import reorder_response

        return reorder_response(
            request,
            self.org,
            DepartmentRole.objects.filter(department=self.dept),
            "position",
            also=("website_position",),
        )


class DepartmentRoleDetailView(DepartmentScopedMixin, APIView):
    read_permission = ROLES_VIEW
    write_permission = DEPT_ROLES_MANAGE

    def get_role(self, pk: int) -> DepartmentRole:
        return get_object_or_404(DepartmentRole, department=self.dept, pk=pk)

    def _keeps_own_admin(self, role: DepartmentRole, new_perms: list[str] | None) -> bool:
        """Verhindert, dass man sich die Rollenverwaltung selbst entzieht.

        Läuft in der Transaktion der Änderung; gleichzeitige Änderungen desselben
        Benutzers warten aufeinander (Gesamtaudit 31.10.b, AT-V05)."""
        User.objects.select_for_update().filter(pk=self.request.user.pk).values_list("pk").first()
        # Nur heute wirksame Rollen: eine erst künftig beginnende ersetzt die heutige
        # nicht (Audit 29.10. ID-F01)
        own_roles = DepartmentRoleHolder.objects.filter(
            membership_id=self.ctx.membership_id,
            role__department=self.dept,
            valid_from__lte=today(),
        ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today()))
        others = [
            h.role
            for h in own_roles.select_related("role")
            if h.role_id != role.pk
            and DEPT_ROLES_MANAGE in effective(h.role.permissions, dept=True)
        ]
        holds = own_roles.filter(role=role).exists()
        if not holds or others:
            return True
        return new_perms is not None and DEPT_ROLES_MANAGE in effective(new_perms, dept=True)

    @transaction.atomic
    def patch(self, request, dept_id: int, pk: int):
        role = self.get_role(pk)
        data = DeptRoleSerializer(
            role, data=request.data, partial=True, context={"dept": self.dept}
        )
        data.is_valid(raise_exception=True)
        new_perms = data.validated_data.get("permissions", role.permissions)
        if not self._keeps_own_admin(role, new_perms):
            raise serializers.ValidationError(
                gettext("Du kannst dir die Rollenverwaltung nicht selbst entziehen.")
            )
        before = snapshot(role)
        role = data.save()
        changes = diff(before, snapshot(role))
        if changes:
            record(self.org, request.user, "update", role, changes)
        return Response(DeptRoleSerializer(role).data)

    @transaction.atomic
    def delete(self, request, dept_id: int, pk: int):
        role = self.get_role(pk)
        if not self._keeps_own_admin(role, None):
            raise serializers.ValidationError(
                gettext("Du kannst dir die Rollenverwaltung nicht selbst entziehen.")
            )
        with transaction.atomic():
            member_services.remove_role_holders(self.org, request.user, role)
            record(self.org, request.user, "delete", role, diff(snapshot(role), {}))
            role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HolderSerializer(serializers.Serializer):
    member = serializers.IntegerField()
    role = serializers.IntegerField()
    valid_from = serializers.DateField(required=False)
    # Vorgänger in derselben Rolle zum Vortag beenden (Rollen-Vorschlag R3)
    end_previous = serializers.BooleanField(required=False, default=False)


def holder_data(h: DepartmentRoleHolder) -> dict:
    person = h.membership.person
    return {
        "id": h.pk,
        "member_id": h.membership_id,
        "member_name": f"{person.first_name} {person.last_name}",
        "role": h.role_id,
        "role_name": h.role.name,
        "valid_from": h.valid_from,
        "valid_until": h.valid_until,
    }


class DepartmentHoldersView(DepartmentScopedMixin, APIView):
    read_permission = ROLES_VIEW
    write_permission = DEPT_ROLES_MANAGE

    def get(self, request, dept_id: int):
        on = today()
        holders = ordered(
            DepartmentRoleHolder.objects.filter(role__department=self.dept)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
            .select_related("membership__person", "role"),
            "role__position",
            "role__name",
            "membership__person__last_name",
        )
        return Response([holder_data(h) for h in holders])

    @transaction.atomic
    def post(self, request, dept_id: int):
        data = HolderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = self.get_member(data.validated_data["member"])
        role = get_object_or_404(
            DepartmentRole, department=self.dept, pk=data.validated_data["role"]
        )
        holder = DepartmentRoleHolder.objects.create(
            organization=self.org,
            membership=membership,
            role=role,
            valid_from=data.validated_data.get("valid_from") or today(),
        )
        record(
            self.org,
            request.user,
            "create",
            holder,
            {"Abteilungsrolle": [None, role.name]},
            person=membership.person,
        )
        ended = []
        if data.validated_data["end_previous"]:
            from access.terms import end_unit_predecessors

            # Die eigene Rollenverwaltung bleibt, wie beim Beenden (siehe unten)
            keep = (
                self.ctx.membership_id
                if DEPT_ROLES_MANAGE in effective(role.permissions, dept=True)
                else None
            )
            ended = end_unit_predecessors(holder, self.org, request.user, keep=keep)
        return Response({**holder_data(holder), "ended": ended}, status=status.HTTP_201_CREATED)


class DepartmentHolderEndView(DepartmentScopedMixin, APIView):
    read_permission = DEPT_ROLES_MANAGE
    write_permission = DEPT_ROLES_MANAGE

    def post(self, request, dept_id: int, pk: int):
        holder = get_object_or_404(
            DepartmentRoleHolder.objects.select_related("membership__person", "role"),
            role__department=self.dept,
            pk=pk,
        )
        if holder.membership_id == self.ctx.membership_id and DEPT_ROLES_MANAGE in effective(
            holder.role.permissions, dept=True
        ):
            raise serializers.ValidationError(
                gettext("Du kannst dir die Rollenverwaltung nicht selbst entziehen.")
            )
        end = today()
        holder.valid_until = max(end, holder.valid_from)
        holder.save(update_fields=["valid_until"])
        record(
            self.org,
            request.user,
            "update",
            holder,
            {"bis": [None, holder.valid_until.isoformat()]},
            person=holder.membership.person,
        )
        return Response(holder_data(holder))


# --- Mitgliederbereich ---


def _portal_access(user, access_id: int) -> PortalAccess:
    access = next((a for a in services.portal_accesses(user) if a.pk == int(access_id)), None)
    if access is None:
        raise NotFound()
    return access


def _bookings_enabled(club) -> bool:
    """Gibt es Objekte, die Mitglieder im Mitgliederbereich anfragen dürfen?"""
    from bookings.portal import portal_items

    return portal_items(club).exists()


def _has_company(access) -> bool:
    from billing.company_portal import has_company

    return has_company(access)


def _is_musician(club, membership_id) -> bool:
    if "music" not in (club.enabled_modules or []):
        return False
    from music.models import Musician

    return Musician.objects.filter(
        organization=club, membership_id=membership_id, active=True
    ).exists()


def portal_summary(access: PortalAccess) -> dict:
    club = access.organization
    with tenant_context(club.pk, access.user_id):
        person = access.membership.person
        first_name, last_name = person.first_name, person.last_name
        if access.contact_person_id is not None:
            # Ansprechpartner: eigener Name, die Mitgliedschaft gehört der Organisation (J5)
            first_name, last_name = services.contact_names(access.contact_person)
        return {
            "id": access.pk,
            "club_id": club.pk,
            "club_name": club.name,
            "club_display_name": club.display_name,
            "first_name": first_name,
            "last_name": last_name,
            "member_kind": person.kind,
            "member_name": person.display_name,
            "date_precision": club.date_precision,
            "theme": effective_theme(club.ancestors()),
            "events_enabled": "events" in (club.enabled_modules or []),
            "entries_enabled": "entries" in (club.enabled_modules or []),
            "competitions_enabled": "competitions" in (club.enabled_modules or []),
            "bookings_enabled": _bookings_enabled(club),
            "helpers_enabled": "helpers" in (club.enabled_modules or []),
            "meetings_enabled": "meetings" in (club.enabled_modules or []),
            "todos_enabled": "todos" in (club.enabled_modules or []),
            "docs_enabled": "docs" in (club.enabled_modules or []),
            "circulars_enabled": "circulars" in (club.enabled_modules or []),
            "cards_enabled": "cards" in (club.enabled_modules or []),
            # Ansprechpartner einer Firma, die für Mitarbeiter zahlt (H5)
            "company": _has_company(access),
            # Musiker sehen in Mein Bereich den Punkt „Musik“ (Menüprüfung 2, N-09)
            "musician": _is_musician(club, access.membership_id),
            # Alle eingeschalteten Module (Modulverzeichnis); die Schalter oben bleiben für
            # ältere App-Stände
            "modules": sorted(club.enabled_modules or []),
            "terms": department_terms(club),
            "imprint_key": ensure_imprint(club).public_key,
        }


@extend_schema(responses=dict)
class MyContextsView(APIView):
    """Abteilungen mit Rechten und Mitgliedschaften im Mitgliederbereich."""

    def get(self, request):
        return Response(
            {
                "departments": [
                    department_summary(ctx)
                    for ctx in sorted(
                        services.department_contexts(request.user).values(),
                        key=lambda c: (c.club.display_name, c.department.display_name),
                    )
                ],
                "portal": [portal_summary(a) for a in services.portal_accesses(request.user)],
            }
        )


class PortalDetailView(APIView):
    def get(self, request, access_id: int):
        access = _portal_access(request.user, access_id)
        club = access.organization
        with tenant_context(club.pk, request.user.pk):
            membership = (
                Membership.objects.select_related("person").filter(pk=access.membership_id).first()
            )
            if membership is None:
                raise NotFound()
            data = dept_member_detail(club, membership, with_access=False)
            current = membership.current_period()
            data["status"] = "active" if current else "former"
            data["contact_changes_need_approval"] = club.contact_changes_need_approval
            data["club"] = {
                "name": club.name,
                "address_extra": club.address_extra,
                "street": club.street,
                "postal_code": club.postal_code,
                "city": club.city,
                "email": club.contact_email,
                "phone": club.contact_phone,
                "website": club.website,
            }
            data["change_requests"] = [
                change_request_data(cr)
                for cr in ChangeRequest.objects.filter(membership=membership).select_related(
                    "membership__person"
                )[:20]
            ]
            data["cancellation"] = cancellation.info(club, membership)
        return Response(data)


class PortalChangeSerializer(serializers.Serializer):
    last_name = serializers.CharField(max_length=100, required=False)
    first_name = serializers.CharField(max_length=100, required=False)
    birth_date = serializers.DateField(required=False)
    gender = serializers.ChoiceField(choices=Gender.choices, required=False, allow_blank=True)
    title = TitleField(required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    street = serializers.CharField(max_length=200, required=False)
    postal_code = serializers.CharField(max_length=10, required=False)
    city = serializers.CharField(max_length=100, required=False)
    country = serializers.CharField(max_length=100, required=False)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PortalChangeRequestView(APIView):
    @transaction.atomic
    def post(self, request, access_id: int):
        access = _portal_access(request.user, access_id)
        club = access.organization
        data = PortalChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        message = values.pop("message", "")
        with tenant_context(club.pk, request.user.pk):
            membership = Membership.objects.select_related("person").get(pk=access.membership_id)
            if membership.person.is_organization:
                # Organisationen haben keinen Vornamen, kein Geburtsdatum, kein Geschlecht
                for key in ("first_name", "birth_date", "gender", "title"):
                    values.pop(key, None)
            previous_values = current_values(club, membership)
            changed = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in values.items()
                if (v.isoformat() if hasattr(v, "isoformat") else v) != previous_values.get(k)
            }
            if not changed:
                raise serializers.ValidationError(gettext("Es wurde nichts geändert."))
            direct = (
                {}
                if club.contact_changes_need_approval
                else {k: v for k, v in changed.items() if k in services.DIRECT_FIELDS}
            )
            pending = {k: v for k, v in changed.items() if k not in direct}
            if direct:
                # Kontaktdaten gelten sofort; update_member schreibt das Protokoll.
                update_member(
                    club,
                    membership,
                    {k: values[k] for k in direct},
                    request.user,
                )
            cr = None
            if pending:
                if ChangeRequest.objects.filter(
                    membership=membership, status=ChangeRequest.Status.PENDING
                ).exists():
                    raise serializers.ValidationError(
                        fill(
                            "Es gibt schon eine offene Meldung. Bitte warten, bis {e_nom} sie ",
                            club,
                        )
                        + "bearbeitet hat."
                    )
                cr = ChangeRequest.objects.create(
                    organization=club,
                    membership=membership,
                    user=request.user,
                    data=pending,
                    previous={k: previous_values.get(k) for k in pending},
                    message=message,
                )
                record(
                    club,
                    request.user,
                    "create",
                    cr,
                    {k: [previous_values.get(k), v] for k, v in pending.items()},
                    person=membership.person,
                )
            return Response(
                {
                    "applied": direct,
                    "request": change_request_data(cr) if cr else None,
                },
                status=status.HTTP_201_CREATED if cr else status.HTTP_200_OK,
            )


class PortalCancellationSerializer(serializers.Serializer):
    exit_date = serializers.DateField(required=False, allow_null=True)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # Bewusst bestätigt: „Ja, ich kündige meine Mitgliedschaft“
    confirm = serializers.BooleanField()


class PortalCancellationView(APIView):
    """Kündigung der eigenen Mitgliedschaft einreichen (POST) oder zurücknehmen (DELETE)."""

    def post(self, request, access_id: int):
        access = _portal_access(request.user, access_id)
        club = access.organization
        data = PortalCancellationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if not v["confirm"]:
            raise serializers.ValidationError(
                {"confirm": gettext("Bitte bestätige, dass du kündigen möchtest.")}
            )
        with tenant_context(club.pk, request.user.pk):
            membership = Membership.objects.select_related("person").get(pk=access.membership_id)
            c = cancellation.submit(
                club, membership, request.user, v.get("exit_date"), v.get("message", "")
            )
            return Response(cancellation.request_data(c), status=status.HTTP_201_CREATED)

    def delete(self, request, access_id: int, pk: int):
        access = _portal_access(request.user, access_id)
        club = access.organization
        with tenant_context(club.pk, request.user.pk):
            membership = Membership.objects.select_related("person").get(pk=access.membership_id)
            c = cancellation.withdraw(club, membership, request.user, pk)
            return Response(cancellation.request_data(c))


# --- Anmeldelinks (ohne Anmeldung erreichbar) ---

RATE = (10, 15 * 60)  # 10 Versuche je 15 Minuten und IP


def _rate_limited(request, kind: str) -> bool:
    return too_many(f"login-link:{kind}:{client_ip(request)}", RATE[0], RATE[1])


class RequestLinkSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginLinkRequestView(APIView):
    """Anmeldelink per E-Mail anfordern. Antwortet immer gleich (keine Kontosuche)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        if _rate_limited(request, "request"):
            return Response(
                {"detail": gettext("Zu viele Versuche. Bitte später erneut.")}, status=429
            )
        data = RequestLinkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"]
        # Versand im Hintergrund: Die Antwortzeit verrät nicht, ob es ein Konto gibt (H-09)
        from django.conf import settings

        from .tasks import send_requested_link

        if getattr(settings, "MAIL_IN_BACKGROUND", False):
            transaction.on_commit(lambda: send_requested_link.delay(email), robust=True)
        else:
            send_requested_link(email)
        return Response(
            {
                "detail": gettext(
                    "Wenn zu dieser Adresse ein Mitgliederzugang besteht, ist ein "
                    "Anmeldelink unterwegs."
                )
            }
        )


class LoginLinkUseView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, token: str):
        # Ohne Anmeldeklassen prüft DRF kein CSRF. Hier ausdrücklich, damit keine fremde
        # Seite einen Browser mit einem eigenen Link in ein anderes Konto einloggt.
        SessionAuthentication().enforce_csrf(request)
        if _rate_limited(request, "use"):
            return Response(
                {"detail": gettext("Zu viele Versuche. Bitte später erneut.")}, status=429
            )
        link = (
            LoginLink.objects.select_related("user")
            .select_for_update(of=("self",))
            .filter(token_hash=hash_token(token))
            .first()
        )
        if link is None or not link.is_open:
            raise NotFound(
                gettext("Der Link ist ungültig oder abgelaufen. Bitte fordere einen neuen an.")
            )
        user = link.user
        set_rls(None, user.pk)
        if not services.link_login_allowed(user):
            raise PermissionDenied(
                gettext("Für dieses Konto ist die Anmeldung nur mit Passwort möglich.")
            )
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        from peering.sso import record

        # Anmeldeweg vermerken (für Anmeldebestätigungen an andere Instanzen)
        record(request, user, "link")
        return Response({"id": user.pk, "email": user.email, "display": user.get_full_name()})
