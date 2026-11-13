"""Schnittstelle der Leitung für Anmelden per App und Online-Abstimmung (Schritt V7)."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.log import record

from . import access, live, services
from .models import Attendance, Poll
from .views import Base, require_members


def live_data(meeting) -> dict:
    voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
    records = list(meeting.attendance.all())
    present = [r for r in records if r.status == Attendance.Status.PRESENT]
    data = {
        "meeting": meeting.pk,
        "organization": meeting.organization_id,
        "status": meeting.status,
        "online_voting": meeting.kind.online_voting,
        "remote_allowed": meeting.kind.remote_allowed,
        "checkin_open": meeting.checkin_open,
        "remote": meeting.remote,
        "live": meeting.status in live.LIVE_STATES,
        "voters": len(voter_ids),
        "present_app": sum(1 for r in present if r.mode == Attendance.Mode.APP),
        "present_online": sum(1 for r in present if r.mode == Attendance.Mode.ONLINE),
        "entitled": live.entitled_count(meeting, voter_ids),
        "polls": [
            live.poll_data(p, voter_ids=voter_ids)
            for p in meeting.polls.select_related("agenda_item", "meeting").prefetch_related(
                "options"
            )
        ],
    }
    if meeting.checkin_open:
        data.update(live.current_code(meeting))
    return data


class LiveInput(serializers.Serializer):
    open = serializers.BooleanField(required=False)
    remote = serializers.BooleanField(required=False)


class LiveView(Base):
    def get(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk)
        return Response(live_data(meeting))

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Anmeldung öffnen oder schließen, Teilnahme aus der Ferne ein- oder ausschalten."""
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        ser = LiveInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        live.open_checkin(
            meeting,
            open_=data.get("open", meeting.checkin_open),
            remote=data.get("remote"),
        )
        record(
            self.scope.org,
            request.user,
            "update",
            meeting,
            {
                _("Anmeldung per App"): [
                    None,
                    _("offen") if meeting.checkin_open else _("beendet"),
                ],
                _("Teilnahme aus der Ferne"): [
                    None,
                    _("erlaubt") if meeting.remote else _("nicht erlaubt"),
                ],
            },
        )
        return Response(live_data(meeting))


class CandidateInput(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    membership = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class PollInput(serializers.Serializer):
    agenda_item = serializers.IntegerField(min_value=1)
    question = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    secret = serializers.BooleanField(required=False, default=False)
    office = serializers.CharField(max_length=200, required=False, allow_blank=True)
    candidates = CandidateInput(many=True, required=False)


class PollsView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        ser = PollInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        item = meeting.agenda.filter(pk=data["agenda_item"]).first()
        if item is None:
            raise ValidationError({"agenda_item": _("Unbekannter Tagesordnungspunkt.")})
        if item.type not in (item.Type.RESOLUTION, item.Type.ELECTION):
            raise ValidationError(
                {"agenda_item": _("Abgestimmt wird nur bei Beschlüssen und Wahlen.")}
            )
        live.create_poll(
            meeting,
            item,
            question=data.get("question", ""),
            secret=data.get("secret", False),
            office=data.get("office", ""),
            candidates=data.get("candidates", []),
        )
        record(
            self.scope.org,
            request.user,
            "update",
            meeting,
            {_("Online-Abstimmung"): [None, _("angelegt")]},
        )
        return Response(live_data(meeting), status=201)


class PollActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["open", "close", "apply"])


class PollDetailView(Base):
    def poll(self, meeting, poll_id):
        return get_object_or_404(meeting.polls.select_related("agenda_item"), pk=poll_id)

    @transaction.atomic
    def post(self, request, pk, poll, **kwargs):
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        target = self.poll(meeting, poll)
        ser = PollActionInput(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]
        if action == "open":
            live.set_poll_status(target, Poll.Status.OPEN)
        elif action == "close":
            live.set_poll_status(target, Poll.Status.CLOSED)
        else:
            live.apply_result(target)
        labels = {"open": _("gestartet"), "close": _("beendet"), "apply": _("übernommen")}
        record(
            self.scope.org,
            request.user,
            "update",
            meeting,
            {_("Online-Abstimmung"): [None, labels[action]]},
        )
        return Response(live_data(meeting))

    @transaction.atomic
    def delete(self, request, pk, poll, **kwargs):
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        target = self.poll(meeting, poll)
        if target.status != Poll.Status.DRAFT:
            raise ValidationError(
                {"detail": _("Eine gestartete Abstimmung lässt sich nicht löschen.")}
            )
        target.delete()
        return Response(live_data(meeting))
