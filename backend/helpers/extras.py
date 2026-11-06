"""Helferdienste, Schritt H4: Plan kopieren, Aufruf per Rundschreiben, geleistete Dienste."""

from __future__ import annotations

import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from audit.log import diff, record, snapshot
from organizations.addresses import base_url

from . import access, services
from .models import HelperPlan, Shift, ShiftAssignment, ShiftQuota
from .views import Base, can_callout, plan_data


class CopyInput(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    days = serializers.IntegerField(min_value=-3660, max_value=3660)
    event = serializers.IntegerField(min_value=1, allow_null=True, required=False)


class CopyView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Plan mit Diensten, Schichten und Kontingenten kopieren, Zeiten um Tage verschoben."""
        access.require_edit(self.scope)
        source = self.plan(pk)
        ser = CopyInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        title = data["title"].strip()
        if not title:
            raise ValidationError({"title": _("Bitte einen Titel angeben.")})
        shift = datetime.timedelta(days=data["days"])
        plan = HelperPlan.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            title=title,
            event=self.event(data.get("event")),
            signup=source.signup,
            cancel_days=source.cancel_days,
            max_shifts=source.max_shifts,
            show_names=source.show_names,
            remind_days=source.remind_days,
            note=source.note,
            created_by=request.user,
        )
        for duty in source.duties.prefetch_related("shifts__quotas"):
            old_shifts = list(duty.shifts.all())
            duty.pk = None
            duty.plan = plan
            duty.save()
            for old in old_shifts:
                quotas = list(old.quotas.all())
                new = Shift.objects.create(
                    organization=self.scope.org,
                    duty=duty,
                    starts_at=old.starts_at + shift,
                    ends_at=old.ends_at + shift,
                    needed=old.needed,
                    note=old.note,
                )
                for q in quotas:
                    if q.department.is_active:
                        ShiftQuota.objects.create(
                            organization=self.scope.org,
                            shift=new,
                            department_id=q.department_id,
                            count=q.count,
                        )
        record(self.scope.org, request.user, "create", plan, diff({}, snapshot(plan)))
        return Response(plan_data(plan, self.scope, full=True), status=201)


def callout_text(plan: HelperPlan) -> tuple[str, str, int]:
    """Betreff, Text mit freien Schichten und Zahl der freien Plätze."""
    from core.i18n import date_text

    now = timezone.now()
    lines = [
        "{Anrede},",
        "",
        _("für **{title}** suchen wir noch Helferinnen und Helfer.").format(title=plan.title),
        "",
    ]
    total = 0
    for duty in plan.duties.prefetch_related("shifts__assignments", "shifts__quotas__assignments"):
        rows = []
        for shift in duty.shifts.all():
            if shift.starts_at <= now:
                continue
            free = max(services.free(shift), 0)
            if not free:
                continue
            total += free
            start = timezone.localtime(shift.starts_at)
            end = timezone.localtime(shift.ends_at)
            rows.append(
                "- "
                + _("{day}, {start}–{end}: {n} frei").format(
                    day=date_text(start), start=f"{start:%H:%M}", end=f"{end:%H:%M}", n=free
                )
            )
        if rows:
            head = f"**{duty.name}**"
            if duty.location:
                head += f" ({duty.location})"
            lines += [head, *rows, ""]
    if plan.signup == HelperPlan.Signup.SELF:
        lines.append(
            _("Trag dich im Mitgliederbereich ein: {url}").format(
                url=f"{base_url(plan.organization)}/mein-bereich/helferdienste"
            )
        )
    else:
        lines.append(_("Bitte melde dich bei der Verwaltung, wenn du helfen kannst."))
    lines += ["", _("Vielen Dank!")]
    subject = _("Helfer gesucht: {title} (noch {n} Plätze frei)").format(title=plan.title, n=total)
    return subject[:200], "\n".join(lines), total


class CalloutView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Rundschreiben-Entwurf „noch Plätze frei“ an die Mitglieder der Einheit."""
        from circulars.models import Circular

        access.require_edit(self.scope)
        if not can_callout(self.scope):
            raise PermissionDenied()
        plan = self.plan(pk)
        if plan.status != HelperPlan.Status.PUBLISHED:
            raise ValidationError({"detail": _("Bitte den Plan zuerst veröffentlichen.")})
        subject, body, total = callout_text(plan)
        if not total:
            raise ValidationError({"detail": _("Alle Schichten sind besetzt.")})
        circular = Circular.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            kind=Circular.Kind.INFO,
            audience=Circular.Audience.MEMBERS,
            subject=subject,
            body=body,
            filters={},
            created_by=request.user,
        )
        record(
            self.scope.org,
            request.user,
            "update",
            plan,
            {_("Aufruf als Rundschreiben"): [None, subject]},
        )
        return Response({"circular": circular.pk}, status=201)


class DoneView(Base):
    """Geleistete Dienste je Person in einem Jahr (für Dank, Ehrungen oder Pflichtstunden)."""

    def get(self, request, **kwargs):
        year = request.query_params.get("jahr") or ""
        year = int(year) if year.isdigit() else timezone.localdate().year
        tz = timezone.get_current_timezone()
        start = datetime.datetime(year, 1, 1, tzinfo=tz)
        end = datetime.datetime(year + 1, 1, 1, tzinfo=tz)
        rows = ShiftAssignment.objects.filter(
            shift__duty__plan__in=self.plans(),
            status=ShiftAssignment.Status.ACTIVE,
            done=True,
            shift__starts_at__gte=start,
            shift__starts_at__lt=end,
        ).select_related("shift")
        people: dict[tuple, dict] = {}
        for a in rows:
            key = ("m", a.membership_id) if a.membership_id else ("x", a.name)
            entry = people.setdefault(
                key,
                {
                    "membership": a.membership_id,
                    "name": a.name,
                    "external": a.membership_id is None,
                    "shifts": 0,
                    "minutes": 0,
                },
            )
            entry["shifts"] += 1
            entry["minutes"] += int((a.shift.ends_at - a.shift.starts_at).total_seconds() // 60)
        result = sorted(people.values(), key=lambda p: (-p["minutes"], p["name"].casefold()))
        return Response({"year": year, "people": result})
