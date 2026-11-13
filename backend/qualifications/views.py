"""Schnittstelle der Qualifikationen: Arten der Einheit, Nachweise am Mitglied, Übersicht."""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import MEMBERS_EDIT, MEMBERS_VIEW, ORG_EDIT
from audit.log import diff, record, snapshot
from core.api_base import AuditMixin, OrgScopedMixin
from core.reorder import reorder_response
from members.models import Membership, today
from organizations.models import Organization

from . import services
from .models import Qualification, QualificationType

ORG_TYPES = (Organization.Type.CLUB, Organization.Type.FEDERATION)


class _ModuleMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not self.org.keeps_members or not services.module_on(self.org):
            raise NotFound()


# --- Arten ---


class TypeSerializer(serializers.ModelSerializer):
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = QualificationType
        fields = [
            "id",
            "name",
            "description",
            "validity_months",
            "remind_days",
            "inspection_only",
            "is_archived",
            "sort_order",
            "in_use",
        ]
        read_only_fields = ["is_archived", "sort_order"]

    def get_in_use(self, obj) -> bool:
        # Die Liste bringt den Wert aus der Hauptabfrage mit (Gesamtaudit 13.11. P-03)
        known = getattr(obj, "in_use_flag", None)
        return obj.records.exists() if known is None else known

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte eine Bezeichnung angeben."))
        qs = QualificationType.objects.filter(organization=self.context["org"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(gettext("Diese Qualifikation gibt es schon."))
        return value

    def validate_validity_months(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError(gettext("Bitte mindestens einen Monat angeben."))
        return value

    def validate(self, attrs):
        if (
            self.instance is not None
            and attrs.get("inspection_only")
            and not (self.instance.inspection_only)
        ):
            if self.instance.records.exclude(note="").exists():
                raise serializers.ValidationError(
                    {
                        "inspection_only": gettext(
                            "Einträge dieser Art haben Bemerkungen. Bitte diese zuerst entfernen."
                        )
                    }
                )
        return attrs


class TypeViewSet(_ModuleMixin, OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    """Qualifikationsarten (lesen: jede Rolle, z. B. für Helferdienste; ändern: Organisation)."""

    serializer_class = TypeSerializer
    allowed_org_types = ORG_TYPES
    write_permission = ORG_EDIT
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def get_queryset(self):
        from django.db.models import Exists, OuterRef

        return QualificationType.objects.filter(organization=self.org).annotate(
            in_use_flag=Exists(Qualification.objects.filter(kind=OuterRef("pk")))
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = getattr(self, "org", None)
        return ctx

    def get_create_kwargs(self) -> dict:
        return {"organization": self.org}

    @action(detail=False, methods=["post"])
    def reorder(self, request, *args, **kwargs):
        return reorder_response(
            request, self.org, QualificationType.objects.filter(organization=self.org), "sort_order"
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        kind = self.get_object()
        if kind.records.exists():
            return Response(
                {
                    "detail": gettext(
                        "„{name}“ ist bei Mitgliedern eingetragen und kann nur archiviert werden."
                    ).format(name=kind.name),
                    "can_archive": not kind.is_archived,
                },
                status=status.HTTP_409_CONFLICT,
            )
        self.perform_destroy(kind)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        record(self.org, self.request.user, "delete", instance, diff(snapshot(instance), {}))
        instance.delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def archive(self, request, org_id: int, pk: int):
        return self._set_archived(True)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def restore(self, request, org_id: int, pk: int):
        return self._set_archived(False)

    def _set_archived(self, archived: bool):
        kind = self.get_object()
        if kind.is_archived != archived:
            kind.is_archived = archived
            kind.save(update_fields=["is_archived"])
            record(
                self.org,
                self.request.user,
                "update",
                kind,
                {"archiviert": [not archived, archived]},
            )
        return Response(self.get_serializer(kind).data)


# --- Nachweise am Mitglied ---


class RecordSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="kind.name", read_only=True)
    inspection_only = serializers.BooleanField(source="kind.inspection_only", read_only=True)
    status = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()

    class Meta:
        model = Qualification
        fields = [
            "id",
            "kind",
            "kind_name",
            "inspection_only",
            "acquired_on",
            "valid_until",
            "note",
            "status",
            "current",
        ]

    def get_fields(self):
        fields = super().get_fields()
        org = self.context.get("org")
        if org is not None:
            fields["kind"].queryset = QualificationType.objects.filter(organization=org)
        return fields

    def get_status(self, obj) -> str:
        return services.status(obj, today())

    def get_current(self, obj) -> bool:
        current = self.context.get("current_ids")
        return current is None or obj.pk in current

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        kind, start = get("kind"), get("acquired_on")
        if self.instance is None and kind is not None and kind.is_archived:
            raise ValidationError({"kind": gettext("Diese Qualifikation ist archiviert.")})
        if start and start > today():
            raise ValidationError({"acquired_on": gettext("Das Datum liegt in der Zukunft.")})
        if self.instance is None and "valid_until" not in attrs and kind and kind.validity_months:
            # Übliche Gültigkeit der Art, wenn kein Ablaufdatum angegeben ist
            attrs["valid_until"] = services.add_months(start, kind.validity_months)
        end = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if end and start and end < start:
            raise ValidationError({"valid_until": gettext("Das Ablaufdatum liegt vor dem Beginn.")})
        if kind is not None and kind.inspection_only:
            # Führungszeugnis & Co.: nur Tatsache und Datum der Einsicht, nie der Inhalt
            if (get("note") or "").strip():
                raise ValidationError(
                    {"note": gettext("Bei einem Einsichtsvermerk ist keine Bemerkung möglich.")}
                )
            attrs["note"] = ""
        return attrs


class MemberRecordViewSet(_ModuleMixin, OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = RecordSerializer
    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_EDIT
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]
    pagination_class = None

    def get_membership(self) -> Membership:
        if not hasattr(self, "_membership"):
            self._membership = get_object_or_404(
                Membership.objects.select_related("person"),
                organization=self.org,
                pk=self.kwargs["member_pk"],
            )
        return self._membership

    def get_queryset(self):
        return Qualification.objects.filter(
            organization=self.org, person_id=self.get_membership().person_id
        ).select_related("kind")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "org", None) is not None:
            ctx["org"] = self.org
            if self.action == "list":
                ctx["current_ids"] = {q.pk for q in services.latest(self.get_queryset()).values()}
        return ctx

    def _record(self, action_: str, instance, changes: dict):
        membership = self.get_membership()
        record(self.org, self.request.user, action_, instance, changes, person=membership.person)

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(
            organization=self.org,
            person_id=self.get_membership().person_id,
            created_by=self.request.user,
        )
        self._record("create", instance, diff({}, snapshot(instance)))

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        old_end = serializer.instance.valid_until
        instance = serializer.save()
        if instance.valid_until != old_end and instance.reminded_at is not None:
            instance.reminded_at = None
            instance.save(update_fields=["reminded_at"])
        changes = diff(before, snapshot(instance))
        changes.pop("reminded_at", None)
        if changes:
            self._record("update", instance, changes)

    @transaction.atomic
    def perform_destroy(self, instance):
        self._record("delete", instance, diff(snapshot(instance), {}))
        instance.delete()


# --- Übersicht ---


class OverviewView(_ModuleMixin, OrgScopedMixin, APIView):
    """Maßgebliche Nachweise aller aktuellen Mitglieder, wahlweise nur bald ablaufende.

    ``?stand=bald`` (läuft bald ab oder abgelaufen), ``?art=<id>``."""

    allowed_org_types = ORG_TYPES
    read_permission = MEMBERS_VIEW

    def get(self, request, org_id: int):
        from members.views import member_queryset

        # Von den Nachweisen ausgehen und nur deren Inhaber laden: Früher wurden erst alle
        # aktuellen Mitglieder samt entschlüsselter Personendaten geholt, auch wenn nur
        # wenige einen Nachweis haben (Gesamtaudit 13.11. P-02)
        qs = Qualification.objects.filter(organization=self.org).select_related("kind")
        kind = request.query_params.get("art")
        if kind:
            if not kind.isdigit():
                raise ValidationError({"art": gettext("Unbekannte Qualifikation.")})
            qs = qs.filter(kind_id=int(kind))
        on = today()
        only_soon = request.query_params.get("stand") == "bald"
        wanted = []
        for q in services.latest(qs).values():
            state = services.status(q, on)
            if only_soon and state == services.VALID:
                continue
            wanted.append((q, state))
        members = {
            m.person_id: m
            for m in member_queryset(self.org)
            .filter(
                is_current=True,
                purged_at__isnull=True,
                person_id__in={q.person_id for q, _ in wanted},
            )
            .select_related("person")
        }
        rows = []
        for q, state in wanted:
            m = members.get(q.person_id)
            if m is None:  # kein aktuelles Mitglied mehr
                continue
            rows.append(
                {
                    "id": q.pk,
                    "member": m.pk,
                    "first_name": m.person.first_name,
                    "last_name": m.person.last_name,
                    "kind": q.kind_id,
                    "kind_name": q.kind.name,
                    "inspection_only": q.kind.inspection_only,
                    "acquired_on": q.acquired_on,
                    "valid_until": q.valid_until,
                    "status": state,
                }
            )
        rows.sort(
            key=lambda r: (
                r["valid_until"] is None,
                r["valid_until"] or on,
                r["last_name"].lower(),
                r["first_name"].lower(),
            )
        )
        return Response(rows)
