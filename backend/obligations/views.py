"""Schnittstelle des Fristenkalenders: Pflichten, Vorschläge, Erledigung mit Nachweis."""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record

from . import access, services
from .catalog import BY_KEY, SUGGESTIONS
from .models import Obligation, ObligationDone

MAX_OBLIGATIONS = 100


def conflict():
    exc = APIException(_("Die Pflicht wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


def registered(org) -> bool:
    from organizations.models import Imprint

    return Imprint.objects.filter(organization=org, registered=True).exists()


def user_name(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def item_data(o: Obligation, scope, user, today) -> dict:
    status = "inactive"
    if o.active and o.trigger == Obligation.Trigger.ELECTION:
        status = "election"
    elif o.active and o.due_date:
        if o.due_date < today:
            status = "overdue"
        elif (o.due_date - today).days <= o.remind_days:
            status = "soon"
        else:
            status = "planned"
    elif not o.active and o.history.exists():
        status = "done"
    return {
        "id": o.pk,
        "key": o.key,
        "title": o.title,
        "note": o.note,
        "trigger": o.trigger,
        "due_date": o.due_date.isoformat() if o.due_date else None,
        "interval_months": o.interval_months,
        "remind_days": o.remind_days,
        "days_after": o.days_after,
        "role": o.role_id,
        "role_name": o.role.name if o.role_id else "",
        "active": o.active,
        "status": status,
        "version": o.version,
        "history": [
            {
                "id": h.pk,
                "due_date": h.due_date.isoformat() if h.due_date else None,
                "done_on": h.done_on.isoformat(),
                "note": h.note,
                "done_by": user_name(h.done_by),
            }
            for h in o.history.select_related("done_by")[:10]
        ],
    }


class ObligationInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)
    key = serializers.CharField(max_length=40, required=False, allow_blank=True)
    title = serializers.CharField(max_length=200, required=False)
    note = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    trigger = serializers.ChoiceField(choices=Obligation.Trigger.choices, required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    interval_months = serializers.IntegerField(
        min_value=1, max_value=120, required=False, allow_null=True
    )
    remind_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    days_after = serializers.IntegerField(min_value=0, max_value=365, required=False)
    role = serializers.IntegerField(required=False, allow_null=True)
    active = serializers.BooleanField(required=False)


class DoneInput(serializers.Serializer):
    done_on = serializers.DateField(required=False)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"))

    def obligations(self):
        return Obligation.objects.filter(organization=self.scope.org).select_related("role")

    def roles(self):
        from access.models import Role

        return Role.objects.filter(organization=self.scope.org, department__isnull=True).order_by(
            "position", "name"
        )

    def role(self, pk):
        if pk is None:
            return None
        role = self.roles().filter(pk=pk).first()
        if role is None:
            raise ValidationError({"role": _("Unbekannte Rolle.")})
        return role

    def apply(self, o: Obligation, data: dict) -> None:
        for field in ("title", "note", "trigger", "remind_days", "days_after", "active"):
            if field in data:
                setattr(o, field, data[field])
        if "due_date" in data:
            o.due_date = data["due_date"]
            o.reminded_for = None
        if "interval_months" in data:
            o.interval_months = data["interval_months"]
        if "role" in data:
            o.role = self.role(data["role"])
        if not (o.title or "").strip():
            raise ValidationError({"title": _("Bitte eine Bezeichnung eingeben.")})
        if o.trigger == Obligation.Trigger.ELECTION:
            o.due_date = None
            o.interval_months = None
        elif o.active and o.due_date is None:
            raise ValidationError({"due_date": _("Bitte eine Frist eingeben.")})


class ListView(Base):
    def get(self, request, **kwargs):
        today = timezone.localdate()
        rows = list(self.obligations())
        taken = {o.key for o in rows if o.key}
        is_registered = registered(self.scope.org)
        return Response(
            {
                "items": [item_data(o, self.scope, request.user, today) for o in rows],
                "suggestions": [
                    s.data(today)
                    for s in SUGGESTIONS
                    if s.key not in taken and (is_registered or not s.registered_only)
                ],
                "roles": [{"id": r.pk, "name": r.name} for r in self.roles()],
                "registered": is_registered,
                "can_edit": self.scope.can_edit,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = ObligationInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        if self.obligations().count() >= MAX_OBLIGATIONS:
            raise ValidationError({"detail": _("Höchstens 100 Pflichten je Einheit.")})
        key = (data.pop("key", "") or "").strip()
        o = Obligation(organization=self.scope.org)
        if key:
            suggestion = BY_KEY.get(key)
            if suggestion is None:
                raise ValidationError({"key": _("Unbekannter Vorschlag.")})
            if self.obligations().filter(key=key).exists():
                raise ValidationError({"key": _("Dieser Vorschlag ist schon übernommen.")})
            defaults = suggestion.data(timezone.localdate())
            o.key = key
            o.title = defaults["title"]
            o.note = defaults["note"]
            o.trigger = suggestion.trigger
            o.interval_months = defaults["interval_months"]
            o.remind_days = suggestion.remind_days
            o.due_date = suggestion.first_due(timezone.localdate())
        self.apply(o, data)
        o.save()
        record(self.scope.org, request.user, "create", o, {_("Vereinspflicht"): [None, o.title]})
        return Response(item_data(o, self.scope, request.user, timezone.localdate()), status=201)


class DetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        o = get_object_or_404(self.obligations().select_for_update(of=("self",)), pk=pk)
        ser = ObligationInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        data.pop("key", None)
        version = data.pop("version", None)
        if version is not None and version != o.version:
            raise conflict()
        before = o.title
        self.apply(o, data)
        o.version += 1
        o.save()
        record(self.scope.org, request.user, "update", o, {_("Vereinspflicht"): [before, o.title]})
        return Response(item_data(o, self.scope, request.user, timezone.localdate()))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        o = get_object_or_404(self.obligations(), pk=pk)
        record(self.scope.org, request.user, "delete", o, {_("Vereinspflicht"): [o.title, None]})
        o.delete()
        return Response(status=204)


class DoneView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Frist als erledigt vermerken; wiederkehrende Pflichten rücken weiter."""
        o = get_object_or_404(self.obligations().select_for_update(of=("self",)), pk=pk)
        if not (self.scope.can_edit or services.holds_role(request.user, o)):
            access.require_edit(self.scope)
        if not o.active or o.trigger != Obligation.Trigger.DATE:
            raise ValidationError({"detail": _("Diese Pflicht hat keine offene Frist.")})
        ser = DoneInput(data=request.data)
        ser.is_valid(raise_exception=True)
        today = timezone.localdate()
        done_on = ser.validated_data.get("done_on") or today
        if done_on > today:
            raise ValidationError({"done_on": _("Das Datum liegt in der Zukunft.")})
        ObligationDone.objects.create(
            organization=self.scope.org,
            obligation=o,
            due_date=o.due_date,
            done_on=done_on,
            note=ser.validated_data.get("note", ""),
            done_by=request.user,
        )
        following = services.next_due(o, done_on)
        if following is None:
            o.active = False
        else:
            o.due_date = following
        o.reminded_for = None
        o.version += 1
        o.save()
        record(
            self.scope.org,
            request.user,
            "update",
            o,
            {_("Erledigt"): [None, f"{o.title} ({done_on:%d.%m.%Y})"]},
        )
        return Response(item_data(o, self.scope, request.user, today))
