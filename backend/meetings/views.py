from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from members.models import MemberType

from . import access, services
from .models import AgendaItem, Meeting, MeetingKind

MAX_AGENDA = 60


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def kinds(self):
        return services.kinds(self.scope)

    def meeting(self, pk, *, lock=False):
        qs = Meeting.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id
        ).select_related("event", "kind", "circular")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)


def can_write_circulars(scope) -> bool:
    codes = {"dept.circulars.send"} if scope.department_id else {"circulars.send", "circulars.edit"}
    return bool(codes & scope.permissions)


def conflict():
    exc = APIException(_("Die Versammlung wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


def kind_data(kind):
    return {
        "id": kind.pk,
        "name": kind.name,
        "base": kind.base,
        "invite_days": kind.invite_days,
        "invite_form": kind.invite_form,
        "voter_types": kind.voter_types,
        "voter_min_age": kind.voter_min_age,
        "quorum_percent": kind.quorum_percent,
        "quorum_count": kind.quorum_count,
        "proxies_allowed": kind.proxies_allowed,
        "minutes_for": kind.minutes_for,
        "position": kind.position,
        "active": kind.active,
        "used": kind.meetings.exists(),
    }


def agenda_data(item):
    return {
        "id": item.pk,
        "position": item.position,
        "title": item.title,
        "description": item.description,
        "type": item.type,
    }


def meeting_data(meeting, scope, *, full=False):
    event = meeting.event
    data = {
        "id": meeting.pk,
        "kind": meeting.kind_id,
        "kind_name": meeting.kind.name,
        "base": meeting.kind.base,
        "title": event.title,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "location": event.location,
        "address": event.address,
        "event": event.pk,
        "status": meeting.status,
        "invite_by": services.invite_by(meeting),
        "invited_at": meeting.invited_at,
        "circular": meeting.circular_id,
        "circular_status": meeting.circular.status if meeting.circular_id else "",
        "version": meeting.version,
        "can_edit": scope.can_edit,
        "can_invite": scope.can_edit and can_write_circulars(scope),
    }
    if full:
        data.update(
            chair=meeting.chair,
            minute_taker=meeting.minute_taker,
            note=meeting.note,
            agenda=[agenda_data(a) for a in meeting.agenda.all()],
        )
    return data


class KindInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    base = serializers.ChoiceField(choices=MeetingKind.Base.choices, required=False)
    invite_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    invite_form = serializers.ChoiceField(choices=MeetingKind.Form.choices, required=False)
    voter_types = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=100, required=False
    )
    voter_min_age = serializers.IntegerField(
        min_value=0, max_value=120, allow_null=True, required=False
    )
    quorum_percent = serializers.IntegerField(
        min_value=1, max_value=100, allow_null=True, required=False
    )
    quorum_count = serializers.IntegerField(
        min_value=1, max_value=100000, allow_null=True, required=False
    )
    proxies_allowed = serializers.BooleanField(required=False)
    minutes_for = serializers.ChoiceField(choices=MeetingKind.MinutesFor.choices, required=False)
    position = serializers.IntegerField(min_value=0, max_value=1000, required=False)
    active = serializers.BooleanField(required=False)


class KindsView(Base):
    def get(self, request, **kwargs):
        return Response([kind_data(k) for k in self.kinds()])

    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        self.kinds()
        kind = MeetingKind(organization=self.scope.org, department_id=self.scope.department_id)
        save_kind(self.scope, kind, request.data, partial=False)
        return Response(kind_data(kind), status=201)


def save_kind(scope, kind, payload, *, partial):
    ser = KindInput(data=payload, partial=partial)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    if "voter_types" in data:
        types = set(data["voter_types"])
        known = set(
            MemberType.objects.filter(organization=scope.org, pk__in=types).values_list(
                "pk", flat=True
            )
        )
        if types - known:
            raise ValidationError({"voter_types": _("Unbekannte Mitgliedsart.")})
        data["voter_types"] = sorted(types)
    if "name" in data:
        name = data["name"].strip()
        if not name:
            raise ValidationError({"name": _("Bitte einen Namen angeben.")})
        clash = MeetingKind.objects.filter(
            organization=scope.org, department_id=scope.department_id, name=name
        ).exclude(pk=kind.pk)
        if clash.exists():
            raise ValidationError({"name": _("Diese Art gibt es schon.")})
        data["name"] = name
    for field, value in data.items():
        setattr(kind, field, value)
    kind.save()


class KindDetailView(Base):
    def kind(self, pk):
        return get_object_or_404(self.kinds(), pk=pk)

    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        kind = self.kind(pk)
        save_kind(self.scope, kind, request.data, partial=True)
        return Response(kind_data(kind))

    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        kind = self.kind(pk)
        if kind.meetings.exists():
            raise ValidationError(
                {"detail": _("Diese Art wird schon verwendet. Sie lässt sich nur abschalten.")}
            )
        kind.delete()
        return Response(status=204)


class MeetingInput(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    kind = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200, required=False)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    location = serializers.CharField(max_length=200, allow_blank=True, required=False)
    address = serializers.CharField(max_length=300, allow_blank=True, required=False)
    chair = serializers.CharField(max_length=200, allow_blank=True, required=False)
    minute_taker = serializers.CharField(max_length=200, allow_blank=True, required=False)
    note = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    status = serializers.ChoiceField(
        choices=[Meeting.Status.DRAFT, Meeting.Status.CANCELLED], required=False
    )
    agenda_from_last = serializers.BooleanField(required=False, default=True)


def _check_times(starts_at, ends_at):
    if ends_at < starts_at:
        raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})


class ListView(Base):
    def get(self, request, **kwargs):
        qs = (
            Meeting.objects.filter(
                organization=self.scope.org, department_id=self.scope.department_id
            )
            .select_related("event", "kind", "circular")
            .order_by("-event__starts_at", "-pk")
        )
        return Response([meeting_data(m, self.scope) for m in qs])

    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = MeetingInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        missing = [f for f in ("kind", "starts_at", "ends_at") if f not in data]
        if missing:
            raise ValidationError({f: _("Pflichtangabe.") for f in missing})
        kind = self.kinds().filter(pk=data["kind"], active=True).first()
        if kind is None:
            raise ValidationError({"kind": _("Unbekannte Art.")})
        _check_times(data["starts_at"], data["ends_at"])
        title = (data.get("title") or "").strip() or kind.name
        meeting = services.create(
            self.scope,
            request.user,
            kind=kind,
            title=title,
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            location=data.get("location", ""),
            address=data.get("address", ""),
            agenda_from_last=data["agenda_from_last"],
        )
        record(self.scope.org, request.user, "create", meeting, diff({}, snapshot(meeting)))
        return Response(meeting_data(meeting, self.scope, full=True), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(meeting_data(self.meeting(pk), self.scope, full=True))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        meeting = self.meeting(pk, lock=True)
        before = snapshot(meeting)
        ser = MeetingInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "version" in data and data["version"] != meeting.version:
            raise conflict()
        event = meeting.event
        if "kind" in data:
            kind = self.kinds().filter(pk=data["kind"]).first()
            if kind is None:
                raise ValidationError({"kind": _("Unbekannte Art.")})
            meeting.kind = kind
        if "title" in data:
            title = data["title"].strip()
            if not title:
                raise ValidationError({"title": _("Bitte einen Titel angeben.")})
            event.title = title
        for field in ("starts_at", "ends_at", "location", "address"):
            if field in data:
                setattr(event, field, data[field])
        _check_times(event.starts_at, event.ends_at)
        for field in ("chair", "minute_taker", "note"):
            if field in data:
                setattr(meeting, field, data[field])
        if "status" in data and data["status"] != meeting.status:
            allowed = {
                Meeting.Status.CANCELLED: {
                    Meeting.Status.DRAFT,
                    Meeting.Status.INVITED,
                },
                Meeting.Status.DRAFT: {Meeting.Status.CANCELLED},
            }
            if meeting.status not in allowed[data["status"]]:
                raise ValidationError({"status": _("Dieser Wechsel ist nicht möglich.")})
            meeting.status = data["status"]
            event.is_cancelled = meeting.status == Meeting.Status.CANCELLED
        event.save()
        meeting.version += 1
        meeting.save()
        changes = diff(before, snapshot(meeting))
        if changes:
            record(self.scope.org, request.user, "update", meeting, changes)
        return Response(meeting_data(meeting, self.scope, full=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        meeting = self.meeting(pk, lock=True)
        if meeting.status not in (Meeting.Status.DRAFT, Meeting.Status.CANCELLED):
            raise ValidationError(
                {"detail": _("Nach der Einladung lässt sich eine Versammlung nur absagen.")}
            )
        event = meeting.event
        record(self.scope.org, request.user, "delete", meeting, diff(snapshot(meeting), {}))
        meeting.delete()
        event.delete()
        return Response(status=204)


class AgendaItemInput(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    type = serializers.ChoiceField(choices=AgendaItem.Type.choices, required=False)


class AgendaInput(serializers.Serializer):
    version = serializers.IntegerField()
    items = AgendaItemInput(many=True, max_length=MAX_AGENDA)


class AgendaView(Base):
    """Tagesordnung als Ganzes speichern (Reihenfolge = Nummerierung)."""

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        meeting = self.meeting(pk, lock=True)
        ser = AgendaInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data["version"] != meeting.version:
            raise conflict()
        if meeting.status not in (Meeting.Status.DRAFT, Meeting.Status.INVITED):
            raise ValidationError(
                {"detail": _("Die Tagesordnung lässt sich jetzt nicht mehr ändern.")}
            )
        existing = {a.pk: a for a in meeting.agenda.all()}
        keep = set()
        for position, entry in enumerate(data["items"], start=1):
            item = existing.get(entry.get("id")) if entry.get("id") else None
            if item is None:
                item = AgendaItem(organization=self.scope.org, meeting=meeting)
            title = entry["title"].strip()
            if not title:
                raise ValidationError({"items": _("Jeder Punkt braucht einen Titel.")})
            item.position = position
            item.title = title
            item.description = entry.get("description", item.description or "")
            item.type = entry.get("type", item.type or AgendaItem.Type.OTHER)
            item.save()
            keep.add(item.pk)
        meeting.agenda.exclude(pk__in=keep).delete()
        meeting.version += 1
        meeting.save(update_fields=["version", "updated_at"])
        return Response(meeting_data(meeting, self.scope, full=True))


class InvitationView(Base):
    """Einladung als Entwurf eines Rundschreibens vorbereiten (Schritt V2)."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        if not can_write_circulars(self.scope):
            raise PermissionDenied(
                _("Für die Einladung ist zusätzlich das Recht nötig, Rundschreiben zu versenden.")
            )
        meeting = self.meeting(pk, lock=True)
        if meeting.status != Meeting.Status.DRAFT:
            raise ValidationError({"detail": _("Zu dieser Versammlung wurde schon eingeladen.")})
        if not meeting.agenda.exists():
            raise ValidationError({"detail": _("Bitte zuerst die Tagesordnung anlegen.")})
        circular = services.prepare_invitation(meeting, request.user)
        record(
            self.scope.org,
            request.user,
            "update",
            meeting,
            {"Einladung": [None, circular.subject]},
        )
        return Response(meeting_data(meeting, self.scope, full=True))
