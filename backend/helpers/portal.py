"""Helferdienste im Mitgliederbereich (Schritt H2).

Mitglieder sehen veröffentlichte Dienstpläne ihres Vereins und ihrer Untereinheiten, tragen
sich in freie Schichten ein und sagen bis zur Frist wieder ab. Danach geht eine Absage nur
über die Verwaltung. „Meine Dienste“ gibt es auch als Kalenderdatei.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import services
from .models import HelperPlan, Shift, ShiftAssignment


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if "helpers" not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership.current_period():
        raise NotFound()
    return access


def visible_plans(access):
    """Veröffentlichte Pläne des Vereins und der eigenen Untereinheiten."""
    from circulars.recipients import club_base

    org = access.organization
    plans = []
    for plan in (
        HelperPlan.objects.filter(organization=org, status=HelperPlan.Status.PUBLISHED)
        .select_related("event", "department")
        .order_by("pk")
    ):
        if plan.department_id is None or (
            club_base(org, plan.department).filter(pk=access.membership_id).exists()
        ):
            plans.append(plan)
    return plans


def cancel_until(plan: HelperPlan, shift: Shift) -> datetime.datetime:
    return shift.starts_at - datetime.timedelta(days=plan.cancel_days)


def plan_data(plan: HelperPlan, membership_id: int, now) -> dict:
    duties = []
    for duty in plan.duties.prefetch_related("shifts__assignments"):
        shifts = []
        for shift in duty.shifts.all():
            people = [a for a in shift.assignments.all() if a.status == "active"]
            mine = next((a for a in people if a.membership_id == membership_id), None)
            shifts.append(
                {
                    "id": shift.pk,
                    "starts_at": shift.starts_at,
                    "ends_at": shift.ends_at,
                    "needed": shift.needed,
                    "taken": len(people),
                    "note": shift.note,
                    "names": [a.name for a in people] if plan.show_names else [],
                    "mine": mine.pk if mine else None,
                    "can_cancel": bool(mine) and now < cancel_until(plan, shift),
                    "past": shift.starts_at <= now,
                }
            )
        duties.append(
            {
                "id": duty.pk,
                "name": duty.name,
                "description": duty.description,
                "location": duty.location,
                "min_age": duty.min_age,
                "shifts": shifts,
            }
        )
    return {
        "id": plan.pk,
        "title": plan.title,
        "unit": plan.department.name if plan.department_id else "",
        "event_title": plan.event.title if plan.event_id else "",
        "signup": plan.signup,
        "cancel_days": plan.cancel_days,
        "max_shifts": plan.max_shifts,
        "note": plan.note,
        "duties": duties,
    }


def mine_data(membership_id: int, org) -> list[dict]:
    rows = (
        ShiftAssignment.objects.filter(
            organization=org,
            membership_id=membership_id,
            status=ShiftAssignment.Status.ACTIVE,
            shift__ends_at__gte=timezone.now() - datetime.timedelta(days=1),
        )
        .select_related("shift__duty__plan")
        .order_by("shift__starts_at")
    )
    return [
        {
            "id": a.pk,
            "plan": a.shift.duty.plan.title,
            "duty": a.shift.duty.name,
            "location": a.shift.duty.location,
            "starts_at": a.shift.starts_at,
            "ends_at": a.shift.ends_at,
        }
        for a in rows
        if a.shift.duty.plan.status != HelperPlan.Status.DRAFT
    ]


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ListView(Base):
    def get(self, request, **kwargs):
        now = timezone.now()
        member = self.access.membership_id
        return Response(
            {
                "plans": [plan_data(p, member, now) for p in visible_plans(self.access)],
                "mine": mine_data(member, self.org),
            }
        )


class SignupView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        plans = {p.pk: p for p in visible_plans(self.access)}
        shift = get_object_or_404(
            Shift.objects.filter(duty__plan_id__in=plans)
            .select_related("duty")
            .select_for_update(of=("self",)),
            pk=pk,
        )
        plan = plans[shift.duty.plan_id]
        membership = self.access.membership
        if plan.signup != HelperPlan.Signup.SELF:
            raise ValidationError({"detail": _("In diesen Plan trägt nur die Verwaltung ein.")})
        if shift.starts_at <= timezone.now():
            raise ValidationError({"detail": _("Die Schicht hat schon begonnen.")})
        if services.active(shift.assignments.filter(membership=membership)).exists():
            raise ValidationError({"detail": _("Du bist schon eingetragen.")})
        if plan.max_shifts:
            count = services.active(
                ShiftAssignment.objects.filter(shift__duty__plan=plan, membership=membership)
            ).count()
            if count >= plan.max_shifts:
                raise ValidationError(
                    {
                        "detail": _(
                            "In diesem Plan sind höchstens {n} Schichten je Person möglich."
                        ).format(n=plan.max_shifts)
                    }
                )
        found = services.warnings(shift, membership)
        if found:
            raise ValidationError({"detail": " ".join(w["text"] for w in found)})
        ShiftAssignment.objects.create(
            organization=self.org,
            shift=shift,
            membership=membership,
            name=services.person_name(membership),
            origin=ShiftAssignment.Origin.SELF,
            created_by=request.user,
        )
        return Response(plan_data(plan, membership.pk, timezone.now()), status=201)


class CancelView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        assignment = get_object_or_404(
            services.active(
                ShiftAssignment.objects.filter(
                    organization=self.org, membership_id=self.access.membership_id
                )
            ).select_related("shift__duty__plan"),
            pk=pk,
        )
        plan = assignment.shift.duty.plan
        if plan.status == HelperPlan.Status.CLOSED or timezone.now() >= cancel_until(
            plan, assignment.shift
        ):
            raise ValidationError(
                {
                    "detail": _(
                        "Die Frist zum Absagen ist vorbei. Bitte wende dich an die Verwaltung."
                    )
                }
            )
        assignment.status = ShiftAssignment.Status.CANCELLED
        assignment.save(update_fields=["status"])
        return Response(status=204)


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


class CalendarView(Base):
    """Eigene Dienste als Kalenderdatei (iCalendar)."""

    def get(self, request, **kwargs):
        stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//HUBIplan//Helferdienste//DE",
            "CALSCALE:GREGORIAN",
        ]
        for row in mine_data(self.access.membership_id, self.org):
            start = row["starts_at"].astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            end = row["ends_at"].astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            lines += [
                "BEGIN:VEVENT",
                f"UID:helferdienst-{row['id']}@hubiplan",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{start}",
                f"DTEND:{end}",
                f"SUMMARY:{_ics_text(row['duty'] + ' · ' + row['plan'])}",
            ]
            if row["location"]:
                lines.append(f"LOCATION:{_ics_text(row['location'])}")
            lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        response = HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar")
        response["Content-Disposition"] = 'attachment; filename="meine-dienste.ics"'
        return response
