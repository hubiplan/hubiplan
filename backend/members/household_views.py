"""Schnittstelle Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1).

- ``households/``                 Liste (``?art=family|company``, ``?ehemalige=1``), Anlegen
- ``households/<id>/``            Lesen, Umbenennen, Löschen (nur ohne aktuelle Mitglieder)
- ``households/<id>/members/``    Mitglied aufnehmen (``membership``, ``role``, ``valid_from``,
  ``move``, ``pays_via``)
- ``households/<id>/members/<link>/``  PATCH: Ende (``valid_until``), Rolle oder
  ``pays_via`` (Beitrag über den Haushalt, H2);
  DELETE: falsch erfassten Eintrag löschen
- ``households/suggestions/``     Mitglieder mit gleicher Anschrift (nur Vorschläge)
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from access.catalog import MEMBERS_EDIT, MEMBERS_VIEW
from audit.log import diff, record, snapshot
from core.api_base import AuditMixin, OrgScopedMixin
from organizations.models import Organization

from . import households
from .models import Household, HouseholdMember, Membership, today


class HouseholdSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Household
        fields = ["id", "kind", "name", "note", "members", "created_at", "updated_at"]
        read_only_fields = ["id", "members", "created_at", "updated_at"]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte einen Namen angeben."))
        return value

    def validate_kind(self, value):
        if self.instance is not None and value != self.instance.kind:
            if self.instance.members.exists():
                raise serializers.ValidationError(
                    gettext("Die Art lässt sich nur ändern, solange niemand zugeordnet ist.")
                )
        return value

    def get_members(self, obj) -> list[dict]:
        on = today()
        past = self.context.get("past", False)
        rows = []
        for link in obj.members.all():
            current = link.current(on) or link.valid_from > on
            if not current and not past:
                continue
            person = link.membership.person
            rows.append(
                {
                    "link": link.pk,
                    "membership": link.membership_id,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "title": person.title,
                    "birth_date": person.birth_date,
                    "role": link.role,
                    "pays_via": link.pays_via,
                    "valid_from": link.valid_from,
                    "valid_until": link.valid_until,
                    "current": current,
                }
            )
        order = {"adult": 0, "child": 1, "": 2}
        rows.sort(
            key=lambda r: (
                not r["current"],
                order.get(r["role"], 2),
                r["birth_date"] is None,
                r["birth_date"] or on,
                r["last_name"].lower(),
            )
        )
        return rows


class HouseholdMemberInput(serializers.Serializer):
    membership = serializers.IntegerField()
    role = serializers.ChoiceField(
        choices=HouseholdMember.Role.values, required=False, allow_blank=True, default=""
    )
    valid_from = serializers.DateField(required=False)
    move = serializers.BooleanField(required=False, default=False)
    pays_via = serializers.BooleanField(required=False, default=False)


class HouseholdLinkUpdate(serializers.Serializer):
    valid_until = serializers.DateField(required=False, allow_null=True)
    role = serializers.ChoiceField(
        choices=HouseholdMember.Role.values, required=False, allow_blank=True
    )
    pays_via = serializers.BooleanField(required=False)


class HouseholdViewSet(OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    """Haushalte und Firmen eines Vereins."""

    allowed_org_types = (Organization.Type.CLUB,)
    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_EDIT
    serializer_class = HouseholdSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def get_queryset(self):
        qs = Household.objects.filter(organization=self.org).prefetch_related(
            Prefetch(
                "members",
                queryset=HouseholdMember.objects.select_related("membership__person"),
            )
        )
        kind = self.request.query_params.get("art")
        if kind in Household.Kind.values:
            qs = qs.filter(kind=kind)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["past"] = self.action != "list" or self.request.query_params.get("ehemalige") == "1"
        return ctx

    def get_create_kwargs(self) -> dict:
        return {"organization": self.org}

    def perform_destroy(self, instance):
        on = today()
        if any(link.current(on) or link.valid_from > on for link in instance.members.all()):
            raise serializers.ValidationError(
                {
                    "detail": gettext(
                        "Der Haushalt hat noch Mitglieder. Bitte zuerst deren Zugehörigkeit "
                        "beenden."
                    )
                }
            )
        from billing.models import Mandate

        if Mandate.objects.filter(household=instance, debits__isnull=False).exists():
            raise serializers.ValidationError(
                {
                    "detail": gettext(
                        "Über ein Mandat dieses Haushalts wurde schon eingezogen. Der Haushalt "
                        "bleibt deshalb erhalten; er ist ohne Mitglieder nur noch unter "
                        "„ehemalige“ zu sehen."
                    )
                }
            )
        super().perform_destroy(instance)

    def _record(self, action_name, link, before):
        record(
            self.org,
            self.request.user,
            action_name,
            link,
            diff(before, snapshot(link) if action_name != "delete" else {}),
            person=link.membership.person,
        )

    @extend_schema(request=HouseholdMemberInput, responses={201: HouseholdSerializer})
    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, org_id: int, pk=None):
        household = self.get_object()
        data = HouseholdMemberInput(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        membership = get_object_or_404(Membership, organization=self.org, pk=v["membership"])
        with transaction.atomic():
            ended = list(
                HouseholdMember.objects.filter(
                    membership=membership, kind=household.kind, valid_until__isnull=True
                )
            )
            before = {e.pk: snapshot(e) for e in ended}
            link = households.add_member(
                household,
                membership,
                role=v.get("role", ""),
                valid_from=v.get("valid_from"),
                move=v.get("move", False),
                pays_via=v.get("pays_via", False),
            )
            for old in ended:
                old.refresh_from_db()
                self._record("update", old, before[old.pk])
            self._record("create", link, {})
        household = self.get_queryset().get(pk=household.pk)
        return Response(self.get_serializer(household).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=HouseholdLinkUpdate,
        responses={200: HouseholdSerializer, 204: None},
        parameters=[OpenApiParameter("link_id", int, OpenApiParameter.PATH)],
    )
    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"members/(?P<link_id>\d+)",
    )
    def change_member(self, request, org_id: int, pk=None, link_id=None):
        household = self.get_object()
        link = get_object_or_404(
            HouseholdMember.objects.select_related("membership__person"),
            household=household,
            pk=link_id,
        )
        before = snapshot(link)
        if request.method == "DELETE":
            with transaction.atomic():
                self._record("delete", link, before)
                link.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        data = HouseholdLinkUpdate(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        with transaction.atomic():
            if "valid_until" in v:
                if v["valid_until"] is None:
                    clash = (
                        HouseholdMember.objects.filter(
                            membership=link.membership, kind=link.kind, valid_until__isnull=True
                        )
                        .exclude(pk=link.pk)
                        .exists()
                    )
                    if clash:
                        raise serializers.ValidationError(
                            {
                                "valid_until": gettext(
                                    "Das Mitglied gehört inzwischen zu einem anderen Haushalt."
                                )
                            }
                        )
                    if link.pays_via:
                        households.check_pays_via(link.membership, exclude=link.pk)
                    link.valid_until = None
                    link.save(update_fields=["valid_until"])
                else:
                    households.end_member(link, v["valid_until"])
            if "role" in v:
                link.role = v["role"] if household.kind == Household.Kind.FAMILY else ""
                link.save(update_fields=["role"])
            if "pays_via" in v and v["pays_via"] != link.pays_via:
                if v["pays_via"] and link.valid_until is None:
                    households.check_pays_via(link.membership, exclude=link.pk)
                link.pays_via = v["pays_via"]
                link.save(update_fields=["pays_via"])
            changes = diff(before, snapshot(link))
            if changes:
                record(
                    self.org,
                    request.user,
                    "update",
                    link,
                    changes,
                    person=link.membership.person,
                )
        household = self.get_queryset().get(pk=household.pk)
        return Response(self.get_serializer(household).data)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"])
    def suggestions(self, request, org_id: int):
        return Response(households.suggestions(self.org))
