"""Versammlungen im Mitgliederbereich (Schritt V5).

Stimmberechtigte sehen anstehende Versammlungen, zu denen eingeladen ist, mit Tagesordnung
und freigegebene Protokolle, wenn die Art sie für alle Stimmberechtigten bestimmt.
Vorstands- und Gremienprotokolle bleiben den Rollen mit Leserecht vorbehalten.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import live, services
from .models import Attendance, Meeting, MeetingKind, Motion, Poll

# Protokolle der letzten Jahre; ältere stehen in der Dokumentenablage
YEARS_BACK = 5
# Anträge je Mitglied und Versammlung
MAX_OWN = 5


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if "meetings" not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership.current_period():
        raise NotFound()
    return access


def is_voter(meeting: Meeting, membership_id: int) -> bool:
    return services.voters(meeting).filter(pk=membership_id).exists()


def visible(access) -> tuple[list[Meeting], list[Meeting]]:
    """Anstehende Versammlungen mit Einladung und freigegebene Protokolle des Mitglieds."""
    now = timezone.now()
    base = Meeting.objects.filter(organization=access.organization).select_related(
        "event", "kind", "organization", "department"
    )
    upcoming = [
        m
        for m in base.filter(
            status=Meeting.Status.INVITED, event__ends_at__gte=now - datetime.timedelta(hours=12)
        ).order_by("event__starts_at")[:20]
        if is_voter(m, access.membership_id)
    ]
    since = now - datetime.timedelta(days=365 * YEARS_BACK)
    minutes = [
        m
        for m in base.filter(
            status=Meeting.Status.DONE,
            kind__minutes_for=MeetingKind.MinutesFor.VOTERS,
            event__starts_at__gte=since,
        ).order_by("-event__starts_at")[:50]
        if is_voter(m, access.membership_id)
    ]
    return upcoming, minutes


def motion_until(meeting: Meeting):
    """Letzter Zeitpunkt für Anträge oder None, wenn die Art keine Anträge vorsieht."""
    days = meeting.kind.motion_days
    if days is None:
        return None
    return meeting.event.starts_at - datetime.timedelta(days=days)


def own_motions(meeting: Meeting, membership_id: int) -> list[dict]:
    return [
        {
            "id": m.pk,
            "title": m.title,
            "text": m.text,
            "status": m.status,
            "reply": m.reply,
            "created_at": m.created_at,
        }
        for m in meeting.motions.filter(membership_id=membership_id)
    ]


def unit_name(meeting: Meeting) -> str:
    return meeting.department.name if meeting.department_id else ""


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ListView(Base):
    def get(self, request, **kwargs):
        upcoming, minutes = visible(self.access)
        return Response(
            {
                "upcoming": [
                    {
                        "id": m.pk,
                        "title": m.event.title,
                        "kind_name": m.kind.name,
                        "unit": unit_name(m),
                        "starts_at": m.event.starts_at,
                        "location": m.event.location,
                        "address": m.event.address,
                        "motion_until": motion_until(m),
                        "checkin_open": m.checkin_open,
                        "remote": m.remote and m.checkin_open,
                        "motions": own_motions(m, self.access.membership_id),
                        "agenda": [
                            {
                                "position": item.position,
                                "level": item.level,
                                "number": item.number,
                                "title": item.title,
                                "description": item.description,
                            }
                            for item in m.agenda.all()
                        ],
                    }
                    for m in upcoming
                ],
                "minutes": [
                    {
                        "id": m.pk,
                        "title": m.event.title,
                        "kind_name": m.kind.name,
                        "unit": unit_name(m),
                        "starts_at": m.event.starts_at,
                    }
                    for m in minutes
                    if m.minutes_versions.exists()
                ],
            }
        )


class MinutesView(Base):
    def get(self, request, pk, **kwargs):
        _upcoming, minutes = visible(self.access)
        meeting = next((m for m in minutes if m.pk == pk), None)
        if meeting is None:
            raise NotFound()
        released = meeting.minutes_versions.first()
        if released is None:
            raise NotFound()
        name = f"protokoll-{timezone.localtime(meeting.event.starts_at):%Y-%m-%d}.pdf"
        response = FileResponse(
            released.file.open("rb"), content_type="application/pdf", filename=name
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MotionInput(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    text = serializers.CharField(max_length=10000)


class MotionsView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Antrag zu einer Versammlung stellen, zu der das Mitglied eingeladen ist."""
        upcoming, _minutes = visible(self.access)
        meeting = next((m for m in upcoming if m.pk == pk), None)
        if meeting is None:
            raise NotFound()
        until = motion_until(meeting)
        if until is None:
            raise ValidationError(
                {"detail": _("Zu dieser Versammlung sind keine Anträge vorgesehen.")}
            )
        if timezone.now() >= until:
            raise ValidationError({"detail": _("Die Frist für Anträge ist vorbei.")})
        ser = MotionInput(data=request.data)
        ser.is_valid(raise_exception=True)
        title = ser.validated_data["title"].strip()
        text = ser.validated_data["text"].strip()
        if not title or not text:
            raise ValidationError({"detail": _("Bitte Titel und Begründung angeben.")})
        if meeting.motions.filter(membership_id=self.access.membership_id).count() >= MAX_OWN:
            raise ValidationError({"detail": _("Du hast schon zu viele Anträge gestellt.")})
        person = self.access.membership.person
        Motion.objects.create(
            organization=meeting.organization,
            meeting=meeting,
            membership_id=self.access.membership_id,
            name=f"{person.first_name} {person.last_name}".strip(),
            title=title,
            text=text,
        )
        return Response(own_motions(meeting, self.access.membership_id), status=201)


class WithdrawView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        motion = Motion.objects.filter(
            organization=self.access.organization,
            membership_id=self.access.membership_id,
            status=Motion.Status.SUBMITTED,
            pk=pk,
        ).first()
        if motion is None:
            raise NotFound()
        motion.status = Motion.Status.WITHDRAWN
        motion.save(update_fields=["status"])
        return Response(status=204)


# --- Anmelden per App und Online-Abstimmung (Schritt V7) -----------------------------------


class LiveBase(Base):
    def live_meeting(self, pk, *, lock=False) -> Meeting:
        qs = Meeting.objects.filter(
            organization=self.access.organization, status__in=live.LIVE_STATES
        ).select_related("event", "kind", "organization", "department")
        if lock:
            qs = qs.select_for_update(of=("self",))
        meeting = qs.filter(pk=pk).first()
        if meeting is None:
            raise NotFound()
        return meeting

    def member_live(self, meeting: Meeting) -> dict:
        membership_id = self.access.membership_id
        voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
        me, allowed = live.entitlements(meeting, membership_id, voter_ids)
        if not meeting.checkin_open and me is None and not allowed:
            raise NotFound()
        involved = me is not None or bool(allowed) or membership_id in voter_ids
        polls = (
            meeting.polls.exclude(status=Poll.Status.DRAFT)
            .select_related("agenda_item", "meeting")
            .prefetch_related("options")
            if involved
            else []
        )
        return {
            "id": meeting.pk,
            "title": meeting.event.title,
            "kind_name": meeting.kind.name,
            "unit": unit_name(meeting),
            "starts_at": meeting.event.starts_at,
            "location": meeting.event.location,
            "checkin_open": meeting.checkin_open,
            "remote": meeting.remote and meeting.checkin_open,
            "voter": membership_id in voter_ids,
            "is_organization": self.access.membership.person.is_organization,
            "status": me.status if me else "",
            "mode": me.mode if me else "",
            "votes": len(allowed),
            "polls": [
                live.poll_data(p, voter_ids=voter_ids, for_membership=membership_id) for p in polls
            ],
        }


class LiveView(LiveBase):
    def get(self, request, pk, **kwargs):
        return Response(self.member_live(self.live_meeting(pk)))


class CheckinInput(serializers.Serializer):
    code = serializers.CharField(max_length=100, required=False, allow_blank=True)
    remote = serializers.BooleanField(required=False, default=False)


class CheckinView(LiveBase):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """„Ich bin da“: mit dem Code vom Bildschirm oder aus der Ferne (``remote``)."""
        meeting = self.live_meeting(pk, lock=True)
        ser = CheckinInput(data=request.data)
        ser.is_valid(raise_exception=True)
        if not meeting.checkin_open:
            raise ValidationError({"detail": _("Die Anmeldung ist nicht geöffnet.")})
        if ser.validated_data["remote"]:
            if not meeting.remote:
                raise ValidationError(
                    {
                        "detail": _(
                            "Bei dieser Versammlung ist keine Teilnahme aus der Ferne vorgesehen."
                        )
                    }
                )
            mode = Attendance.Mode.ONLINE
        else:
            if not live.code_valid(meeting, ser.validated_data.get("code", "")):
                raise ValidationError(
                    {"code": _("Der Code ist abgelaufen. Bitte den aktuellen Code scannen.")}
                )
            mode = Attendance.Mode.APP
        live.check_in(meeting, self.access.membership, mode=mode)
        return Response(self.member_live(meeting))


class LeaveView(LiveBase):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """„Ich gehe“: abmelden, Vollmachten fallen weg."""
        meeting = self.live_meeting(pk, lock=True)
        live.check_out(meeting, self.access.membership)
        return Response(self.member_live(meeting))


class VoteInput(serializers.Serializer):
    class Vote(serializers.Serializer):
        attendance = serializers.IntegerField(min_value=1)
        option = serializers.IntegerField(min_value=1)

    votes = Vote(many=True, max_length=100)


class VoteView(LiveBase):
    @transaction.atomic
    def post(self, request, pk, poll, **kwargs):
        meeting = self.live_meeting(pk, lock=True)
        target = meeting.polls.filter(pk=poll).select_related("meeting").first()
        if target is None:
            raise NotFound()
        ser = VoteInput(data=request.data)
        ser.is_valid(raise_exception=True)
        live.cast(target, self.access.membership_id, ser.validated_data["votes"])
        return Response(self.member_live(meeting))
