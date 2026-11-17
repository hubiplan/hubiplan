"""Schnittstelle der Beitragsnachweise.

Verein (``/api/orgs/<id>/…``):

- ``fee-proofs/discounts/``: Ermäßigungen mit Nachweis (ändern: Beiträge bearbeiten)
- ``fee-proofs/settings/``: automatische Anerkennung
- ``fee-proofs/``: Warteschlange und Liste (``?status=``, ``?year=``)
- ``fee-proofs/overview/``: Stand aller zugeordneten Mitglieder je Jahr
- ``fee-proofs/<id>/decide/``, ``fee-proofs/<id>/file/``, ``fee-proofs/<id>/`` (löschen)
- ``members/<id>/fee-discounts/``: Zuordnung am Mitglied
- ``members/<id>/fee-proofs/``: Stand und Nachweise am Mitglied, Eintrag durch den Vorstand

Mitgliederbereich und App: ``/api/portal/<Zugang>/fee-proofs/``.
Persönlicher Link: ``/api/public/fee-proof/<Geheimnis>/``.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import BILLING_EDIT, MEMBERS_EDIT, MEMBERS_VIEW
from audit.log import diff, record, snapshot
from core.api_base import OrgScopedMixin
from core.ratelimit import TooMany, client_ip, too_many
from core.tenancy import rls_bypass, scope_of, set_rls, user_view
from members.models import Membership, MemberType, today
from organizations.models import Organization

from . import services
from .models import DiscountAssignment, FeeProof, ProofDiscount, ProofLink, ProofSettings

ORG_TYPES = (Organization.Type.CLUB, Organization.Type.FEDERATION)
LINK_RATE = (60, 600)
UPLOAD_RATE = (10, 3600)


class _ModuleMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not services.module_on(self.org):
            raise NotFound()


# --- Ermäßigungen ---


class ProofDiscountSerializer(serializers.ModelSerializer):
    member_type = serializers.PrimaryKeyRelatedField(
        queryset=MemberType.objects.all(), allow_null=True, required=False
    )
    member_type_name = serializers.CharField(
        source="member_type.name", read_only=True, default=None
    )
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = ProofDiscount
        fields = [
            "id",
            "name",
            "member_type",
            "member_type_name",
            "amount",
            "discount_percent",
            "deadline_month",
            "deadline_day",
            "grace_days",
            "late_join_days",
            "remind_month",
            "remind_day",
            "remind_before_days",
            "notify_after",
            "kinds",
            "is_archived",
            "sort_order",
            "in_use",
        ]
        read_only_fields = ["sort_order"]

    def get_in_use(self, obj) -> bool:
        return obj.assignments.exists() or obj.proofs.exists()

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte eine Bezeichnung angeben."))
        qs = ProofDiscount.objects.filter(organization=self.context["org"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(gettext("Diese Ermäßigung gibt es schon."))
        return value

    def validate_member_type(self, value):
        if value is not None and value.organization_id != self.context["org"].pk:
            raise serializers.ValidationError(gettext("Unbekannte Mitgliedsart."))
        return value

    def validate_kinds(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError(gettext("Bitte eine Liste von Bezeichnungen."))
        clean = []
        for v in value:
            v = v.strip()[:100]
            if v and v not in clean:
                clean.append(v)
        if len(clean) > 20:
            raise serializers.ValidationError(gettext("Höchstens 20 Arten."))
        return clean

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        errors = {}
        amount, percent = get("amount"), get("discount_percent")
        if (amount is None) == (percent is None):
            errors["amount"] = gettext(
                "Bitte entweder einen ermäßigten Beitrag oder einen Abschlag angeben."
            )
        if amount is not None and amount < 0:
            errors["amount"] = gettext("Der Beitrag darf nicht negativ sein.")
        if percent is not None and not (0 < percent <= 100):
            errors["discount_percent"] = gettext("Der Abschlag liegt zwischen 0 und 100 Prozent.")
        month, day = get("deadline_month") or 2, get("deadline_day") or 28
        try:
            datetime.date(2024, month, day)
        except ValueError:
            errors["deadline_day"] = gettext("Diesen Tag gibt es nicht.")
        r_month, r_day = get("remind_month"), get("remind_day")
        if (r_month is None) != (r_day is None):
            errors["remind_day"] = gettext("Bitte Tag und Monat angeben oder beides leer lassen.")
        elif r_month is not None:
            try:
                datetime.date(2024, r_month, r_day)
            except ValueError:
                errors["remind_day"] = gettext("Diesen Tag gibt es nicht.")
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class DiscountViewSet(_ModuleMixin, OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = ProofDiscountSerializer
    allowed_org_types = ORG_TYPES
    write_permission = BILLING_EDIT
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def get_queryset(self):
        return ProofDiscount.objects.filter(organization=self.org).select_related("member_type")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = getattr(self, "org", None)
        return ctx

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save(organization=self.org)
        record(self.org, self.request.user, "create", obj, diff({}, snapshot(obj)))

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        obj = serializer.save()
        record(self.org, self.request.user, "update", obj, diff(before, snapshot(obj)))

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.assignments.exists() or obj.proofs.exists():
            return Response(
                {
                    "detail": gettext(
                        "„{name}“ ist bei Mitgliedern eingetragen. Bitte stattdessen „nicht mehr "
                        "verwendet“ ankreuzen."
                    ).format(name=obj.name)
                },
                status=status.HTTP_409_CONFLICT,
            )
        record(self.org, request.user, "delete", obj, diff(snapshot(obj), {}))
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SettingsView(_ModuleMixin, OrgScopedMixin, APIView):
    allowed_org_types = ORG_TYPES
    write_permission = BILLING_EDIT

    def data(self) -> dict:
        from billing.incoming_mail import mailbox_address

        cfg = ProofSettings.objects.filter(organization=self.org).first()
        return {
            "auto_accept": bool(cfg and cfg.auto_accept),
            "mail_replies": bool(mailbox_address()),
        }

    def get(self, request, org_id: int):
        return Response(self.data())

    @transaction.atomic
    def patch(self, request, org_id: int):
        value = request.data.get("auto_accept")
        if not isinstance(value, bool):
            raise ValidationError({"auto_accept": gettext("Bitte ja oder nein angeben.")})
        cfg, _created = ProofSettings.objects.get_or_create(organization=self.org)
        if cfg.auto_accept != value:
            record(
                self.org,
                request.user,
                "update",
                cfg,
                {"automatisch anerkennen": [cfg.auto_accept, value]},
            )
            cfg.auto_accept = value
            cfg.save(update_fields=["auto_accept", "updated_at"])
        return Response(self.data())


# --- Darstellung ---


def proof_data(proof: FeeProof, *, member: bool = False) -> dict:
    org = proof.organization
    data = {
        "id": proof.pk,
        "discount": proof.discount_id,
        "discount_name": proof.discount.name,
        "year": proof.year,
        "year_label": org.fiscal_label(proof.year),
        "kind": proof.kind,
        "status": proof.status,
        "channel": proof.channel,
        "received_on": proof.received_on,
        "valid_until": proof.valid_until,
        "has_file": bool(proof.file),
        "file_name": proof.file_name,
        "content_type": proof.content_type,
        "note": proof.note if proof.status in ("question", "rejected") else "",
        "member_note": proof.member_note,
        "late": proof.late,
        "outside_deadline": proof.outside_deadline,
        "reviewed_at": proof.reviewed_at,
    }
    if not member:
        data["precheck"] = proof.precheck or {}
        data["auto_accepted"] = proof.auto_accepted
        data["membership"] = proof.membership_id
        data["file_deleted"] = bool(proof.file_deleted_at)
    return data


def state_data(st: services.YearState, org, *, member: bool = False) -> dict:
    return {
        "discount": st.discount.pk,
        "discount_name": st.discount.name,
        "kinds": list(st.discount.kinds or []),
        "year": st.year,
        "year_label": org.fiscal_label(st.year),
        "due": st.dates.due,
        "final": st.dates.final,
        "state": st.state,
        "applies": st.applies,
        "proof": proof_data(st.proof, member=member) if st.proof is not None else None,
    }


def file_response(proof: FeeProof):
    from core.virenscan import ensure_released

    if not proof.file:
        raise NotFound()
    ensure_released(proof.file)
    response = FileResponse(
        proof.file.open("rb"),
        content_type=proof.content_type,
        as_attachment=False,
        filename=proof.file_name or "nachweis",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _upload(request) -> tuple[str, str, bytes | None]:
    upload = request.FILES.get("file")
    if upload is None:
        return "", "", None
    data = upload.read()
    return upload.name or "", upload.content_type or "", data


# --- Warteschlange und Übersicht ---


def _members_by_id(org, ids) -> dict[int, Membership]:
    return {
        m.pk: m
        for m in Membership.objects.filter(organization=org, pk__in=list(ids)).select_related(
            "person"
        )
    }


class ProofListView(_ModuleMixin, OrgScopedMixin, APIView):
    """Nachweise; ``?status=received`` (Vorgabe: offen = eingegangen und Rückfrage), ``all``."""

    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_VIEW

    def get(self, request, org_id: int):
        qs = FeeProof.objects.filter(organization=self.org).select_related(
            "discount", "organization"
        )
        wanted = request.query_params.get("status", "open")
        if wanted == "open":
            qs = qs.filter(status__in=(FeeProof.Status.RECEIVED, FeeProof.Status.QUESTION))
        elif wanted in FeeProof.Status.values:
            qs = qs.filter(status=wanted)
        elif wanted != "all":
            raise ValidationError({"status": gettext("Unbekannter Stand.")})
        year = request.query_params.get("year")
        if year:
            if not year.isdigit():
                raise ValidationError({"year": gettext("Unbekanntes Jahr.")})
            qs = qs.filter(year=int(year))
        rows = list(qs.order_by("received_on", "pk")[:500])
        members = _members_by_id(self.org, {p.membership_id for p in rows})
        out = []
        for p in rows:
            m = members.get(p.membership_id)
            if m is None:
                continue
            item = proof_data(p)
            item["first_name"] = m.person.first_name
            item["last_name"] = m.person.last_name
            out.append(item)
        return Response(out)


class OverviewView(_ModuleMixin, OrgScopedMixin, APIView):
    """Stand aller Mitglieder mit Ermäßigung für ein Beitragsjahr (``?year=``, Vorgabe: laufendes),
    ``?stand=zwei-jahre``: nur Vorschläge zum Beenden (zwei Jahre ohne Nachweis)."""

    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_VIEW

    def get(self, request, org_id: int):
        on = today()
        org = self.org
        if request.query_params.get("stand") == "zwei-jahre":
            from .open_tasks import stale_assignments

            rows = []
            for a in stale_assignments(org, on):
                person = a.membership.person
                rows.append(
                    {
                        "assignment": a.pk,
                        "membership": a.membership_id,
                        "first_name": person.first_name,
                        "last_name": person.last_name,
                        "discount_name": a.discount.name,
                        "valid_from": a.valid_from,
                    }
                )
            rows.sort(key=lambda r: (r["last_name"].lower(), r["first_name"].lower()))
            return Response({"stale": rows})
        year = request.query_params.get("year")
        if year and not year.isdigit():
            raise ValidationError({"year": gettext("Unbekanntes Jahr.")})
        year = int(year) if year else org.fiscal_year_of(on)
        start, end = org.fiscal_range(year)
        assignments = list(
            DiscountAssignment.objects.filter(organization=org, valid_from__lte=end)
            .exclude(valid_until__lt=start)
            .select_related("discount")
        )
        by_member: dict[int, list[DiscountAssignment]] = {}
        for a in assignments:
            by_member.setdefault(a.membership_id, []).append(a)
        members = _members_by_id(org, by_member)
        proofs: dict[tuple[int, int], list[FeeProof]] = {}
        for p in FeeProof.objects.filter(organization=org, year=year).select_related(
            "discount", "organization"
        ):
            proofs.setdefault((p.membership_id, p.discount_id), []).append(p)
        rows = []
        counts = {k: 0 for k in ("accepted", "pending", "question", "open", "missing")}
        for mid, items in by_member.items():
            m = members.get(mid)
            if m is None or m.purged_at is not None:
                continue
            periods = list(m.periods.all())
            if not any(
                p.entry_date <= end and (p.exit_date is None or p.exit_date >= start)
                for p in periods
            ):
                continue
            for discount in {a.discount_id: a.discount for a in items}.values():
                st = services.year_state(
                    m,
                    discount,
                    year,
                    on,
                    assignments=[a for a in items if a.discount_id == discount.pk],
                    periods=periods,
                    proofs=proofs.get((mid, discount.pk), []),
                )
                counts[st.state] += 1
                row = state_data(st, org)
                row["membership"] = mid
                row["first_name"] = m.person.first_name
                row["last_name"] = m.person.last_name
                rows.append(row)
        rows.sort(key=lambda r: (r["last_name"].lower(), r["first_name"].lower()))
        return Response(
            {"year": year, "year_label": org.fiscal_label(year), "counts": counts, "rows": rows}
        )


class DecideSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "reject", "question"])
    valid_until = serializers.DateField(required=False, allow_null=True)
    kind = serializers.CharField(required=False, allow_blank=True, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ProofDetailView(_ModuleMixin, OrgScopedMixin, APIView):
    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_EDIT
    write_permission = MEMBERS_EDIT

    def get_proof(self, pk: int) -> FeeProof:
        return get_object_or_404(
            FeeProof.objects.select_related("discount", "organization", "membership__person"),
            organization=self.org,
            pk=pk,
        )

    def get(self, request, org_id: int, pk: int, action: str = ""):
        if action != "file":
            raise NotFound()
        return file_response(self.get_proof(pk))

    @transaction.atomic
    def post(self, request, org_id: int, pk: int, action: str = ""):
        if action != "decide":
            raise NotFound()
        proof = self.get_proof(pk)
        ser = DecideSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        before = snapshot(proof)
        services.decide(
            proof,
            ser.validated_data["action"],
            request.user,
            valid_until=ser.validated_data.get("valid_until"),
            kind=ser.validated_data.get("kind"),
            note=ser.validated_data.get("note", ""),
        )
        changes = diff(before, snapshot(proof))
        record(self.org, request.user, "update", proof, changes, person=proof.membership.person)
        return Response(proof_data(proof))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int, action: str = ""):
        if action:
            raise NotFound()
        proof = self.get_proof(pk)
        record(
            self.org,
            request.user,
            "delete",
            proof,
            diff(snapshot(proof), {}),
            person=proof.membership.person,
        )
        services.drop_file(proof)
        proof.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- am Mitglied ---


class _MemberMixin(_ModuleMixin, OrgScopedMixin):
    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_EDIT

    def get_membership(self) -> Membership:
        if not hasattr(self, "_membership"):
            self._membership = get_object_or_404(
                Membership.objects.select_related("person", "organization"),
                organization=self.org,
                pk=self.kwargs["member_pk"],
            )
        return self._membership


class DiscountAssignmentSerializer(serializers.ModelSerializer):
    discount_name = serializers.CharField(source="discount.name", read_only=True)

    class Meta:
        model = DiscountAssignment
        fields = ["id", "discount", "discount_name", "valid_from", "valid_until"]

    def get_fields(self):
        fields = super().get_fields()
        org = self.context.get("org")
        if org is not None:
            fields["discount"].queryset = ProofDiscount.objects.filter(organization=org)
        return fields

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        discount, start, end = get("discount"), get("valid_from"), get("valid_until")
        if self.instance is None and discount is not None and discount.is_archived:
            raise ValidationError(
                {"discount": gettext("Diese Ermäßigung wird nicht mehr verwendet.")}
            )
        if start and end and end < start:
            raise ValidationError({"valid_until": gettext("Das Ende liegt vor dem Beginn.")})
        others = DiscountAssignment.objects.filter(
            membership=self.context["membership"], discount=discount
        )
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        for o in others:
            if (end is None or o.valid_from <= end) and (
                o.valid_until is None or o.valid_until >= start
            ):
                raise ValidationError(
                    {
                        "valid_from": gettext(
                            "Diese Ermäßigung ist für den Zeitraum schon eingetragen."
                        )
                    }
                )
        return attrs


class MemberAssignmentViewSet(_MemberMixin, viewsets.ModelViewSet):
    serializer_class = DiscountAssignmentSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def get_queryset(self):
        return DiscountAssignment.objects.filter(
            organization=self.org, membership=self.get_membership()
        ).select_related("discount")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "org", None) is not None:
            ctx["org"] = self.org
            ctx["membership"] = self.get_membership()
        return ctx

    def _record(self, action_: str, instance, changes: dict):
        record(
            self.org,
            self.request.user,
            action_,
            instance,
            changes,
            person=self.get_membership().person,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save(
            organization=self.org, membership=self.get_membership(), created_by=self.request.user
        )
        self._record("create", obj, diff({}, snapshot(obj)))

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        obj = serializer.save()
        self._record("update", obj, diff(before, snapshot(obj)))

    @transaction.atomic
    def perform_destroy(self, instance):
        self._record("delete", instance, diff(snapshot(instance), {}))
        instance.delete()


class MemberProofsView(_MemberMixin, APIView):
    """GET: Stand je offenem Jahr und alle Nachweise · POST: Nachweis eintragen (Vorstand), mit
    Datei oder als Einsichtsvermerk (dann gleich anerkannt)."""

    def get(self, request, org_id: int, member_pk: int):
        m = self.get_membership()
        proofs = FeeProof.objects.filter(organization=self.org, membership=m).select_related(
            "discount", "organization"
        )
        return Response(
            {
                "states": [state_data(st, self.org) for st in services.requirements(m, today())],
                "proofs": [proof_data(p) for p in proofs.order_by("-year", "-received_on", "-pk")],
            }
        )

    @transaction.atomic
    def post(self, request, org_id: int, member_pk: int):
        m = self.get_membership()
        discount = ProofDiscount.objects.filter(
            organization=self.org, pk=request.data.get("discount")
        ).first()
        if discount is None:
            raise ValidationError({"discount": gettext("Bitte eine Ermäßigung wählen.")})
        year = request.data.get("year")
        try:
            year = int(year)
        except (TypeError, ValueError):
            raise ValidationError({"year": gettext("Bitte ein Beitragsjahr angeben.")}) from None
        if not DiscountAssignment.objects.filter(membership=m, discount=discount).exists():
            raise ValidationError(
                {"discount": gettext("Diese Ermäßigung ist dem Mitglied nicht zugeordnet.")}
            )
        received = request.data.get("received_on") or today().isoformat()
        try:
            received_on = datetime.date.fromisoformat(str(received))
        except ValueError:
            raise ValidationError({"received_on": gettext("Ungültiges Datum.")}) from None
        if received_on > today():
            raise ValidationError({"received_on": gettext("Das Datum liegt in der Zukunft.")})
        name, content_type, data = _upload(request)
        proof = services.submit(
            m,
            discount,
            year,
            channel=FeeProof.Channel.BOARD,
            name=name,
            content_type=content_type,
            data=data,
            kind=request.data.get("kind") or "",
            user=request.user,
            on=received_on,
            check_window=False,
        )
        if not data or str(request.data.get("accept", "")).lower() in ("1", "true", "on"):
            # Einsichtsvermerk (Papier gesehen) oder sofort anerkannt
            until = request.data.get("valid_until") or None
            services.decide(
                proof,
                "accept",
                request.user,
                valid_until=datetime.date.fromisoformat(until) if until else None,
                kind=request.data.get("kind") or proof.kind,
            )
        record(self.org, request.user, "create", proof, diff({}, snapshot(proof)), person=m.person)
        return Response(proof_data(proof), status=status.HTTP_201_CREATED)


# --- Mitgliederbereich und App ---


def _portal_access(user, access_id):
    from portal.views import _portal_access as find

    with user_view(user.pk):
        access = find(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if access.contact_person_id is not None or access.membership_id is None:
        raise NotFound()
    if not services.module_on(access.organization):
        raise NotFound()
    return access


def _channel(request) -> str:
    authenticator = getattr(request, "successful_authenticator", None)
    name = type(authenticator).__name__ if authenticator is not None else ""
    return FeeProof.Channel.APP if "Device" in name or "App" in name else FeeProof.Channel.PORTAL


def member_view(membership, on: datetime.date) -> dict:
    org = membership.organization
    proofs = FeeProof.objects.filter(membership=membership).select_related(
        "discount", "organization"
    )
    return {
        "states": [
            state_data(st, org, member=True) for st in services.requirements(membership, on)
        ],
        "proofs": [
            proof_data(p, member=True) for p in proofs.order_by("-year", "-received_on", "-pk")[:50]
        ],
    }


class PortalProofsView(APIView):
    """GET: offene Jahre mit Stand und eigene Nachweise · POST (mehrteilig): einreichen."""

    def get(self, request, access_id: int):
        access = _portal_access(request.user, access_id)
        membership = Membership.objects.select_related("person", "organization").get(
            pk=access.membership_id
        )
        return Response(member_view(membership, today()))

    @transaction.atomic
    def post(self, request, access_id: int):
        access = _portal_access(request.user, access_id)
        membership = Membership.objects.select_related("person", "organization").get(
            pk=access.membership_id
        )
        key = f"fee-proof-upload:{membership.pk}"
        if too_many(key, UPLOAD_RATE[0], UPLOAD_RATE[1]):
            raise TooMany(key, "versuche")
        discount = ProofDiscount.objects.filter(
            organization=membership.organization, pk=request.data.get("discount")
        ).first()
        if discount is None:
            raise ValidationError({"discount": gettext("Bitte eine Ermäßigung wählen.")})
        try:
            year = int(request.data.get("year"))
        except (TypeError, ValueError):
            raise ValidationError({"year": gettext("Bitte ein Beitragsjahr angeben.")}) from None
        name, content_type, data = _upload(request)
        if not data:
            raise ValidationError({"file": gettext("Bitte eine Datei wählen.")})
        services.submit(
            membership,
            discount,
            year,
            channel=_channel(request),
            name=name,
            content_type=content_type,
            data=data,
            kind=request.data.get("kind") or "",
            member_note=request.data.get("note") or "",
            user=request.user,
        )
        return Response(member_view(membership, today()), status=status.HTTP_201_CREATED)


# --- persönlicher Link ---


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class PublicLinkView(APIView):
    """GET: Angaben zum Link · POST (mehrteilig): Nachweis hochladen."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def resolve(self, request, token: str, *, lock: bool = False) -> ProofLink:
        from .notify import digest

        key = f"fee-proof-link:{client_ip(request)}"
        if too_many(key, LINK_RATE[0], LINK_RATE[1]):
            raise TooMany(key, "aufrufe")
        invalid = gettext("Dieser Link ist ungültig oder abgelaufen.")
        with rls_bypass():
            qs = ProofLink.objects.select_related(
                "organization", "membership__person", "membership__organization", "discount"
            )
            if lock:
                qs = qs.select_for_update(of=("self",))
            link = qs.filter(token_hash=digest(token or "")).first()
            if (
                link is None
                or link.valid_until < timezone.localdate()
                or not services.module_on(link.organization)
                or link.membership.purged_at is not None
            ):
                raise NotFound(invalid)
        return link

    def data(self, link: ProofLink) -> dict:
        from organizations.imprint import ensure as ensure_imprint

        with rls_bypass():
            m = link.membership
            st = services.year_state(m, link.discount, link.year, today())
            imprint_key = ensure_imprint(link.organization).public_key
            proofs = FeeProof.objects.filter(
                membership=m, discount=link.discount, year=link.year
            ).select_related("discount", "organization")
            return {
                "club": link.organization.name,
                "imprint_key": imprint_key,
                "first_name": m.person.first_name,
                "state": state_data(st, link.organization, member=True),
                "proofs": [proof_data(p, member=True) for p in proofs],
            }

    def get(self, request, token: str):
        return _no_store(Response(self.data(self.resolve(request, token))))

    @transaction.atomic
    def post(self, request, token: str):
        link = self.resolve(request, token, lock=True)
        key = f"fee-proof-link-upload:{link.pk}"
        if too_many(key, UPLOAD_RATE[0], UPLOAD_RATE[1]):
            raise TooMany(key, "versuche")
        name, content_type, data = _upload(request)
        if not data:
            raise ValidationError({"file": gettext("Bitte eine Datei wählen.")})
        with rls_bypass():
            services.submit(
                link.membership,
                link.discount,
                link.year,
                channel=FeeProof.Channel.LINK,
                name=name,
                content_type=content_type,
                data=data,
                kind=request.data.get("kind") or "",
                member_note=request.data.get("note") or "",
                check_window=False,
            )
            link.used_at = timezone.now()
            link.save(update_fields=["used_at"])
        return _no_store(Response(self.data(link), status=status.HTTP_201_CREATED))
