"""Schnittstelle der Helferdienste (Schritt H1): Pläne, Dienste, Schichten, Einteilung."""

import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot

from . import access, exports, services
from .models import Duty, HelperPlan, Shift, ShiftAssignment

MAX_DUTIES = 50
MAX_SHIFTS = 100


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def plans(self):
        return HelperPlan.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id
        )

    def plan(self, pk, *, lock=False):
        qs = self.plans().select_related("event")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def duty(self, pk):
        return get_object_or_404(
            Duty.objects.filter(plan__in=self.plans()).select_related("plan"), pk=pk
        )

    def shift(self, pk, *, lock=False):
        qs = Shift.objects.filter(duty__plan__in=self.plans()).select_related("duty__plan")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def assignment(self, pk):
        return get_object_or_404(
            ShiftAssignment.objects.filter(shift__duty__plan__in=self.plans()).select_related(
                "shift__duty__plan"
            ),
            pk=pk,
        )

    def event(self, pk):
        from events.models import Event

        if not pk:
            return None
        event = Event.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id, pk=pk
        ).first()
        if event is None:
            raise ValidationError({"event": _("Unbekannter Termin.")})
        return event


def conflict():
    exc = APIException(_("Der Dienstplan wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


def require_open(plan: HelperPlan) -> None:
    if plan.status == HelperPlan.Status.CLOSED:
        raise ValidationError({"detail": _("Der Dienstplan ist abgeschlossen.")})


def assignment_data(a: ShiftAssignment, scope) -> dict:
    data = {
        "id": a.pk,
        "membership": a.membership_id,
        "name": a.name,
        "external": a.membership_id is None,
        "origin": a.origin,
        "status": a.status,
        "done": a.done,
    }
    if scope.can_edit:
        data["phone"] = a.phone
    return data


def shift_data(shift: Shift, scope) -> dict:
    rows = [assignment_data(a, scope) for a in shift.assignments.all()]
    return {
        "id": shift.pk,
        "starts_at": shift.starts_at,
        "ends_at": shift.ends_at,
        "needed": shift.needed,
        "note": shift.note,
        "taken": sum(1 for a in rows if a["status"] == ShiftAssignment.Status.ACTIVE),
        "assignments": rows,
    }


def duty_data(duty: Duty, scope) -> dict:
    return {
        "id": duty.pk,
        "name": duty.name,
        "description": duty.description,
        "location": duty.location,
        "min_age": duty.min_age,
        "position": duty.position,
        "shifts": [shift_data(s, scope) for s in duty.shifts.all()],
    }


def plan_data(plan: HelperPlan, scope, *, full=False, counts=None) -> dict:
    data = {
        "id": plan.pk,
        "title": plan.title,
        "event": plan.event_id,
        "event_title": plan.event.title if plan.event_id else "",
        "event_starts_at": plan.event.starts_at if plan.event_id else None,
        "status": plan.status,
        "signup": plan.signup,
        "cancel_days": plan.cancel_days,
        "max_shifts": plan.max_shifts,
        "show_names": plan.show_names,
        "version": plan.version,
        "can_edit": scope.can_edit,
    }
    if counts is not None:
        data.update(counts)
    if full:
        duties = plan.duties.prefetch_related("shifts__assignments")
        data["note"] = plan.note
        data["duties"] = [duty_data(d, scope) for d in duties]
        needed = sum(s["needed"] for d in data["duties"] for s in d["shifts"])
        taken = sum(min(s["taken"], s["needed"]) for d in data["duties"] for s in d["shifts"])
        data.update(needed=needed, open=needed - taken)
    return data


class PlanInput(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    title = serializers.CharField(max_length=200, required=False)
    event = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    status = serializers.ChoiceField(choices=HelperPlan.Status.choices, required=False)
    signup = serializers.ChoiceField(choices=HelperPlan.Signup.choices, required=False)
    cancel_days = serializers.IntegerField(min_value=0, max_value=60, required=False)
    max_shifts = serializers.IntegerField(
        min_value=1, max_value=50, allow_null=True, required=False
    )
    show_names = serializers.BooleanField(required=False)
    note = serializers.CharField(max_length=5000, allow_blank=True, required=False)


PLAN_FIELDS = ("signup", "cancel_days", "max_shifts", "show_names", "note")


class ListView(Base):
    def get(self, request, **kwargs):
        qs = self.plans().select_related("event").order_by("-created_at", "-pk")
        rows = []
        for plan in qs:
            shifts = Shift.objects.filter(duty__plan=plan).annotate(
                active=Count(
                    "assignments", filter=Q(assignments__status=ShiftAssignment.Status.ACTIVE)
                )
            )
            needed = sum(s.needed for s in shifts)
            open_ = sum(max(s.needed - s.active, 0) for s in shifts)
            rows.append(plan_data(plan, self.scope, counts={"needed": needed, "open": open_}))
        return Response(rows)

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = PlanInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError({"title": _("Bitte einen Titel angeben.")})
        plan = HelperPlan(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            title=title,
            event=self.event(data.get("event")),
            created_by=request.user,
        )
        for field in PLAN_FIELDS:
            if field in data:
                setattr(plan, field, data[field])
        plan.save()
        record(self.scope.org, request.user, "create", plan, diff({}, snapshot(plan)))
        return Response(plan_data(plan, self.scope, full=True), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(plan_data(self.plan(pk), self.scope, full=True))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        plan = self.plan(pk, lock=True)
        before = snapshot(plan)
        ser = PlanInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "version" in data and data["version"] != plan.version:
            raise conflict()
        if "title" in data:
            title = data["title"].strip()
            if not title:
                raise ValidationError({"title": _("Bitte einen Titel angeben.")})
            plan.title = title
        if "event" in data:
            plan.event = self.event(data["event"])
        for field in PLAN_FIELDS:
            if field in data:
                setattr(plan, field, data[field])
        if "status" in data:
            plan.status = data["status"]
        plan.version += 1
        plan.save()
        changes = diff(before, snapshot(plan))
        if changes:
            record(self.scope.org, request.user, "update", plan, changes)
        return Response(plan_data(plan, self.scope, full=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        plan = self.plan(pk, lock=True)
        if plan.status == HelperPlan.Status.PUBLISHED:
            raise ValidationError(
                {"detail": _("Einen veröffentlichten Plan bitte zuerst abschließen.")}
            )
        record(self.scope.org, request.user, "delete", plan, diff(snapshot(plan), {}))
        plan.delete()
        return Response(status=204)


class DutyInput(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False)
    location = serializers.CharField(max_length=200, allow_blank=True, required=False)
    min_age = serializers.IntegerField(min_value=1, max_value=99, allow_null=True, required=False)
    position = serializers.IntegerField(min_value=0, max_value=1000, required=False)


def _apply_duty(duty: Duty, data: dict) -> None:
    if "name" in data:
        name = data["name"].strip()
        if not name:
            raise ValidationError({"name": _("Bitte einen Namen angeben.")})
        duty.name = name
    for field in ("description", "location", "min_age", "position"):
        if field in data:
            setattr(duty, field, data[field])


class DutiesView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        plan = self.plan(pk, lock=True)
        require_open(plan)
        if plan.duties.count() >= MAX_DUTIES:
            raise ValidationError({"detail": _("Zu viele Dienste in diesem Plan.")})
        ser = DutyInput(data=request.data)
        ser.is_valid(raise_exception=True)
        if not (ser.validated_data.get("name") or "").strip():
            raise ValidationError({"name": _("Bitte einen Namen angeben.")})
        duty = Duty(organization=self.scope.org, plan=plan, position=plan.duties.count())
        _apply_duty(duty, ser.validated_data)
        duty.save()
        return Response(duty_data(duty, self.scope), status=201)


class DutyDetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        duty = self.duty(pk)
        require_open(duty.plan)
        ser = DutyInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        _apply_duty(duty, ser.validated_data)
        duty.save()
        return Response(duty_data(duty, self.scope))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        duty = self.duty(pk)
        require_open(duty.plan)
        if active_in(Shift.objects.filter(duty=duty)):
            raise ValidationError({"detail": _("In diesem Dienst sind noch Personen eingeteilt.")})
        duty.delete()
        return Response(status=204)


def active_in(shifts) -> bool:
    return services.active(ShiftAssignment.objects.filter(shift__in=shifts)).exists()


class ShiftInput(serializers.Serializer):
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    needed = serializers.IntegerField(min_value=1, max_value=500, required=False)
    note = serializers.CharField(max_length=200, allow_blank=True, required=False)
    # Schnelleingabe: Tag und „14-18, 18-22“
    day = serializers.DateField(required=False)
    quick = serializers.CharField(max_length=300, required=False)


class ShiftsView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Eine Schicht oder mehrere per Schnelleingabe anlegen."""
        access.require_edit(self.scope)
        duty = self.duty(pk)
        require_open(duty.plan)
        ser = ShiftInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data.get("quick"):
            if "day" not in data:
                raise ValidationError({"day": _("Pflichtangabe.")})
            try:
                slots = services.parse_quick(data["quick"], data["day"])
            except ValueError as exc:
                raise ValidationError(
                    {"quick": _("„{part}“ ist keine Zeitangabe wie 14-18.").format(part=exc)}
                ) from exc
        else:
            missing = [f for f in ("starts_at", "ends_at") if f not in data]
            if missing:
                raise ValidationError({f: _("Pflichtangabe.") for f in missing})
            slots = [(data["starts_at"], data["ends_at"])]
        if not slots:
            raise ValidationError({"quick": _("Bitte mindestens ein Zeitfenster angeben.")})
        if duty.shifts.count() + len(slots) > MAX_SHIFTS:
            raise ValidationError({"detail": _("Zu viele Schichten in diesem Dienst.")})
        created = []
        for start, end in slots:
            if end <= start:
                raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})
            created.append(
                Shift.objects.create(
                    organization=self.scope.org,
                    duty=duty,
                    starts_at=start,
                    ends_at=end,
                    needed=data.get("needed", 1),
                    note=data.get("note", ""),
                )
            )
        return Response([shift_data(s, self.scope) for s in created], status=201)


class ShiftDetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        shift = self.shift(pk, lock=True)
        require_open(shift.duty.plan)
        ser = ShiftInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        for field in ("starts_at", "ends_at", "needed", "note"):
            if field in data:
                setattr(shift, field, data[field])
        if shift.ends_at <= shift.starts_at:
            raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})
        shift.save()
        return Response(shift_data(shift, self.scope))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        shift = self.shift(pk, lock=True)
        require_open(shift.duty.plan)
        if active_in([shift]):
            raise ValidationError({"detail": _("In dieser Schicht sind noch Personen eingeteilt.")})
        shift.delete()
        return Response(status=204)


class AssignInput(serializers.Serializer):
    membership = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    force = serializers.BooleanField(required=False, default=False)


class AssignmentsView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Person einteilen. Hinweise (voll, Überschneidung, Alter) erst bestätigen lassen."""
        access.require_edit(self.scope)
        shift = self.shift(pk, lock=True)
        require_open(shift.duty.plan)
        ser = AssignInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        membership = None
        if data.get("membership"):
            membership = get_object_or_404(
                services.members(self.scope).select_related("person"), pk=data["membership"]
            )
            if services.active(shift.assignments.filter(membership=membership)).exists():
                raise ValidationError({"membership": _("Die Person ist schon eingeteilt.")})
            name = services.person_name(membership)
        else:
            name = (data.get("name") or "").strip()
            if not name:
                raise ValidationError({"name": _("Bitte einen Namen angeben.")})
        found = services.warnings(shift, membership)
        if found and not data["force"]:
            raise ValidationError(
                {
                    "detail": " ".join(w["text"] for w in found),
                    "warnings": [w["code"] for w in found],
                }
            )
        assignment = ShiftAssignment.objects.create(
            organization=self.scope.org,
            shift=shift,
            membership=membership,
            name=name,
            phone="" if membership else (data.get("phone") or "").strip(),
            origin=ShiftAssignment.Origin.ASSIGNED,
            created_by=request.user,
        )
        record(
            self.scope.org,
            request.user,
            "update",
            shift.duty.plan,
            {_("Eingeteilt"): [None, f"{name} · {services.shift_label(shift)}"]},
        )
        return Response(assignment_data(assignment, self.scope), status=201)


class AssignmentInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=ShiftAssignment.Status.choices, required=False)
    done = serializers.BooleanField(allow_null=True, required=False)


class AssignmentDetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        assignment = self.assignment(pk)
        ser = AssignmentInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "status" in data:
            require_open(assignment.shift.duty.plan)
            assignment.status = data["status"]
        if "done" in data:
            assignment.done = data["done"]
        assignment.save()
        return Response(assignment_data(assignment, self.scope))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        assignment = self.assignment(pk)
        shift = assignment.shift
        require_open(shift.duty.plan)
        record(
            self.scope.org,
            request.user,
            "update",
            shift.duty.plan,
            {_("Eingeteilt"): [f"{assignment.name} · {services.shift_label(shift)}", None]},
        )
        assignment.delete()
        return Response(status=204)


class MembersView(Base):
    """Mitglieder zum Einteilen suchen (nur Namen, nur mit Bearbeitungsrecht)."""

    def get(self, request, **kwargs):
        from members.personsearch import filter_names, ordered

        access.require_edit(self.scope)
        term = (request.query_params.get("suche") or "").strip()
        if len(term) < 2:
            return Response([])
        qs = filter_names(services.members(self.scope), term)
        rows = ordered(qs.select_related("person"), limit=10)
        return Response(
            [
                {"id": m.pk, "first_name": m.person.first_name, "last_name": m.person.last_name}
                for m in rows
            ]
        )


class EventsView(Base):
    """Anstehende Termine der Einheit, an die ein Dienstplan gehängt werden kann."""

    def get(self, request, **kwargs):
        from events.models import Event

        access.require_edit(self.scope)
        since = timezone.now() - datetime.timedelta(days=30)
        qs = Event.objects.filter(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            starts_at__gte=since,
        ).order_by("starts_at")[:200]
        return Response([{"id": e.pk, "title": e.title, "starts_at": e.starts_at} for e in qs])


class ExportView(Base):
    """Aushang je Dienst und Gesamtliste als PDF oder Excel."""

    def get(self, request, pk, **kwargs):
        plan = self.plan(pk)
        fmt = request.query_params.get("datei", "pdf")
        if fmt == "xlsx":
            content = exports.xlsx(plan, with_phone=self.scope.can_edit)
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            content = exports.pdf(plan, with_phone=self.scope.can_edit)
            ctype = "application/pdf"
            fmt = "pdf"
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="dienstplan-{plan.pk}.{fmt}"'
        response["Cache-Control"] = "private, no-store"
        return response
