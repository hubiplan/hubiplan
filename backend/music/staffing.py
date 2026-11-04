"""Besetzungsvorlagen und atomare Sammeleinteilung in bestehende Auftritte."""

from collections import Counter

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.api_base import OrgScopedMixin

from .models import (
    Assignment,
    EnsembleTemplate,
    EnsembleTemplatePosition,
    Musician,
    Performance,
    Position,
)
from .scores import voice
from .views import MusicViewSet, PerformanceViewSet, ScopedSerializer


class TemplatePositionInput(serializers.Serializer):
    instrument = serializers.CharField(max_length=100)
    register = serializers.CharField(max_length=100, allow_blank=True, default="")
    required = serializers.IntegerField(min_value=1, max_value=500)


class EnsembleTemplateSerializer(ScopedSerializer):
    positions = TemplatePositionInput(many=True, min_length=1, max_length=100)

    class Meta:
        model = EnsembleTemplate
        fields = ["id", "name", "note", "active", "positions"]

    def validate_positions(self, rows):
        keys = [voice(r["instrument"], r["register"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError(
                gettext("Jede Instrumentenstimme darf in der Vorlage nur einmal vorkommen.")
            )
        return rows

    def create(self, validated_data):
        positions = validated_data.pop("positions")
        instance = super().create(validated_data)
        self.save_positions(instance, positions)
        return instance

    def update(self, instance, validated_data):
        positions = validated_data.pop("positions", None)
        instance = super().update(instance, validated_data)
        if positions is not None:
            instance.positions.all().delete()
            self.save_positions(instance, positions)
        return instance

    @staticmethod
    def save_positions(instance, positions):
        for row in positions:
            EnsembleTemplatePosition.objects.create(
                organization=instance.organization, template=instance, **row
            )


class EnsembleTemplateViewSet(MusicViewSet):
    serializer_class = EnsembleTemplateSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("positions")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = idempotency.claim(request, f"music.template.{self.org.pk}", required=True)
        if key.done:
            return Response(key.result, status=201)
        response = super().create(request, *args, **kwargs)
        key.remember(response.data)
        return response

    @transaction.atomic
    def perform_create(self, serializer):
        super().perform_create(serializer)
        record(
            self.org,
            self.request.user,
            "update",
            serializer.instance,
            {"Besetzungsvorlage": [None, serializer.data["positions"]]},
        )

    @transaction.atomic
    def perform_update(self, serializer):
        self._lock_and_refresh(serializer.instance)
        serializer = self._revalidate(serializer)
        before = list(serializer.instance.positions.values("instrument", "register", "required"))
        super().perform_update(serializer)
        after = list(serializer.instance.positions.values("instrument", "register", "required"))
        if before != after:
            record(
                self.org,
                self.request.user,
                "update",
                serializer.instance,
                {"Besetzungsvorlage": [before, after]},
            )


class AssignmentInput(serializers.Serializer):
    musician = serializers.IntegerField(min_value=1)
    position = serializers.IntegerField(min_value=1)


class BatchInput(serializers.Serializer):
    assignments = AssignmentInput(many=True, min_length=1, max_length=500)


def staffing_data(performance):
    assigned = list(performance.assignments.order_by("pk"))
    reserved = Counter(a.position_id for a in assigned if a.status != "declined")
    positions = list(performance.positions.order_by("pk"))
    musicians = (
        Musician.objects.filter(organization=performance.organization, active=True)
        .select_related("membership__person")
        .prefetch_related("skills")
    )
    already = {a.musician_id for a in assigned}
    candidates = []
    for m in musicians:
        if m.pk in already:
            continue
        skills = {(s.instrument, s.register) for s in m.skills.all()}
        matching = [p.pk for p in positions if (p.instrument, p.register) in skills]
        if matching:
            candidates.append(
                {
                    "id": m.pk,
                    "name": str(m.membership.person) if m.membership_id else m.name,
                    "positions": matching,
                }
            )
    names = {
        m.pk: str(m.membership.person) if m.membership_id else m.name
        for m in Musician.objects.filter(organization=performance.organization).select_related(
            "membership__person"
        )
    }
    return {
        "title": performance.event.title,
        "cancelled": performance.event.is_cancelled,
        "positions": [
            {
                "id": p.pk,
                "instrument": p.instrument,
                "register": p.register,
                "required": p.required,
                "assigned": reserved[p.pk],
            }
            for p in positions
        ],
        "assignments": [
            {
                "id": a.pk,
                "musician": a.musician_id,
                "name": names.get(a.musician_id, ""),
                "position": a.position_id,
                "status": a.status,
            }
            for a in assigned
        ],
        "candidates": candidates,
    }


class StaffingView(OrgScopedMixin, APIView):
    allowed_org_types = ("club", "federation")
    read_permission = "music.view"
    write_permission = "music.edit"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules:
            raise NotFound()

    def performance(self, pk, lock=False):
        qs = Performance.objects.select_related("event")
        if lock:
            qs = qs.select_for_update(of=("self",))
        obj = get_object_or_404(qs, pk=pk, organization=self.org)
        if not PerformanceViewSet.visible(self, obj):
            raise NotFound()
        return obj

    def get(self, request, org_id, pk):
        return Response(staffing_data(self.performance(pk)))

    @transaction.atomic
    def post(self, request, org_id, pk):
        performance = self.performance(pk, lock=True)
        key = idempotency.claim(request, f"music.staffing.{self.org.pk}", required=True)
        if key.done:
            return Response(key.result)
        action = serializers.ChoiceField(
            choices=["apply_template", "assign", "save_template"]
        ).run_validation(request.data.get("action"))
        if action == "save_template":
            data = {
                "name": request.data.get("name"),
                "note": request.data.get("note", ""),
                "positions": list(
                    performance.positions.order_by("pk").values(
                        "instrument", "register", "required"
                    )
                ),
            }
            serializer = EnsembleTemplateSerializer(data=data, context={"view": self})
            serializer.is_valid(raise_exception=True)
            template = serializer.save(organization=self.org)
            record(
                self.org,
                request.user,
                "create",
                template,
                {"Besetzungsvorlage": [None, serializer.data]},
            )
            result = {"template": template.pk}
        elif action == "apply_template":
            template_id = serializers.IntegerField(min_value=1).run_validation(
                request.data.get("template")
            )
            template = get_object_or_404(
                EnsembleTemplate.objects.select_for_update(),
                pk=template_id,
                organization=self.org,
                active=True,
            )
            self.apply_template(performance, template, request.user)
            result = {"ok": True}
        else:
            if performance.event.is_cancelled:
                raise serializers.ValidationError(
                    gettext("Für abgesagte Auftritte ist keine Sammeleinteilung möglich.")
                )
            serializer = BatchInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = self.assign(
                performance, serializer.validated_data["assignments"], request.user
            )
        key.remember(result)
        return Response(result)

    def apply_template(self, performance, template, user):
        template_rows = list(template.positions.order_by("pk"))
        check = TemplatePositionInput(
            data=[
                {"instrument": p.instrument, "register": p.register, "required": p.required}
                for p in template_rows
            ],
            many=True,
            min_length=1,
            max_length=100,
        )
        check.is_valid(raise_exception=True)
        EnsembleTemplateSerializer().validate_positions(check.validated_data)
        existing = {}
        for p in performance.positions.select_for_update().order_by("pk"):
            existing.setdefault(voice(p.instrument, p.register), []).append(p)
        plan = []
        for row in template_rows:
            matches = existing.get(voice(row.instrument, row.register), [])
            if len(matches) > 1:
                raise serializers.ValidationError(
                    gettext(
                        "Die Besetzungsstimme ist im Auftritt mehrfach vorhanden. "
                        "Bitte zuerst die Positionen bereinigen."
                    )
                )
            plan.append((row, matches[0] if matches else None))
        for row, position in plan:
            before = position.required if position else None
            if position is None:
                position = Position.objects.create(
                    organization=self.org,
                    performance=performance,
                    instrument=row.instrument,
                    register=row.register,
                    required=row.required,
                )
            else:
                position.required = max(position.required, row.required)
                position.save(update_fields=["required"])
            if before != position.required:
                record(
                    self.org,
                    user,
                    "create" if before is None else "update",
                    position,
                    {"Sollbesetzung": [before, position.required]},
                )

    def assign(self, performance, rows, user):
        ids = [r["musician"] for r in rows]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                gettext("Jeder Musiker darf nur einmal ausgewählt werden.")
            )
        musicians = {
            m.pk: m
            for m in Musician.objects.select_for_update()
            .filter(organization=self.org, pk__in=ids, active=True)
            .order_by("pk")
            .prefetch_related("skills")
        }
        positions = {p.pk: p for p in performance.positions.select_for_update().order_by("pk")}
        existing = {
            a.musician_id: a for a in performance.assignments.select_for_update().order_by("pk")
        }
        reserved = Counter(a.position_id for a in existing.values() if a.status != "declined")
        pending = []
        for row in rows:
            musician, position = musicians.get(row["musician"]), positions.get(row["position"])
            if musician is None or position is None:
                raise NotFound()
            old = existing.get(musician.pk)
            if old:
                if old.position_id == position.pk and old.status != "declined":
                    continue
                raise serializers.ValidationError(
                    gettext(
                        "Dieser Musiker ist bereits eingeteilt oder hat abgesagt. "
                        "Bitte die bestehende Einteilung einzeln bearbeiten."
                    )
                )
            if not any(
                s.instrument == position.instrument and s.register == position.register
                for s in musician.skills.all()
            ):
                raise serializers.ValidationError(
                    gettext("Für diese Stimme fehlt die instrumentale Fähigkeit.")
                )
            reserved[position.pk] += 1
            if reserved[position.pk] > position.required:
                raise serializers.ValidationError(
                    gettext(
                        "Die Auswahl überschreitet die freie Sollbesetzung. "
                        "Bitte die Auswahl oder die Sollzahl anpassen."
                    )
                )
            pending.append((musician, position))
        for musician, position in pending:
            assignment = Assignment.objects.create(
                organization=self.org,
                performance=performance,
                musician=musician,
                position=position,
                status="pending",
            )
            record(
                self.org,
                user,
                "create",
                assignment,
                {
                    "Einteilung": [
                        None,
                        {"musician": musician.pk, "position": position.pk, "status": "pending"},
                    ]
                },
            )
        return {"created": len(pending)}
