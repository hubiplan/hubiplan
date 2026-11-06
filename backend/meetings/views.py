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
from .models import AgendaItem, Attendance, Meeting, MeetingKind, Resolution

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


def resolution_data(r):
    return {
        "id": r.pk,
        "kind": r.kind,
        "text": r.text,
        "votes_yes": r.votes_yes,
        "votes_no": r.votes_no,
        "votes_abstain": r.votes_abstain,
        "unanimous": r.unanimous,
        "result": r.result,
        "office": r.office,
        "elected_name": r.elected_name,
        "elected": r.elected_id,
        "number": r.number,
    }


def agenda_data(item, resolutions=None):
    data = {
        "id": item.pk,
        "position": item.position,
        "title": item.title,
        "description": item.description,
        "type": item.type,
    }
    if resolutions is not None:
        data["minutes"] = item.minutes
        data["resolutions"] = [resolution_data(r) for r in resolutions.get(item.pk, [])]
    return data


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
        "can_attendance": members_allowed(scope),
    }
    if full:
        resolutions = {}
        for r in meeting.resolutions.all():
            resolutions.setdefault(r.agenda_item_id, []).append(r)
        data.update(
            chair=meeting.chair,
            minute_taker=meeting.minute_taker,
            note=meeting.note,
            agenda=[agenda_data(a, resolutions) for a in meeting.agenda.all()],
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
        choices=[Meeting.Status.DRAFT, Meeting.Status.HELD, Meeting.Status.CANCELLED],
        required=False,
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
                # Nach der Versammlung: Protokoll schreiben (V4)
                Meeting.Status.HELD: {Meeting.Status.DRAFT, Meeting.Status.INVITED},
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


# --- Anwesenheit (Schritt V3) ---------------------------------------------------------------

OPEN_FOR_ATTENDANCE = (Meeting.Status.DRAFT, Meeting.Status.INVITED, Meeting.Status.HELD)


def members_allowed(scope) -> bool:
    codes = {"members.view", "dept.members.view"} if scope.department_id else {"members.view"}
    return bool(codes & scope.permissions)


def require_members(scope) -> None:
    if not members_allowed(scope):
        raise PermissionDenied(
            _("Für die Anwesenheitsliste ist zusätzlich das Leserecht auf Mitglieder nötig.")
        )


def person_name(membership) -> str:
    person = membership.person
    return f"{person.first_name} {person.last_name}".strip()


def attendance_data(meeting, scope):
    from members.personsearch import ordered

    eligible = list(ordered(services.voters(meeting).select_related("person")))
    voter_ids = {m.pk for m in eligible}
    records = list(meeting.attendance.select_related("represented_by"))
    by_member = {r.membership_id: r for r in records if r.membership_id}
    rows = []
    for m in eligible:
        r = by_member.get(m.pk)
        rows.append(
            {
                "id": r.pk if r else None,
                "membership": m.pk,
                "name": person_name(m),
                "voter": True,
                "status": r.status if r else "",
                "represented_by": r.represented_by_id if r else None,
            }
        )
    others = [r for r in records if r.membership_id not in voter_ids]
    others.sort(key=lambda r: r.name.lower())
    for r in others:
        rows.append(
            {
                "id": r.pk,
                "membership": r.membership_id,
                "name": r.name,
                "voter": False,
                "status": r.status,
                "represented_by": r.represented_by_id,
            }
        )
    present = sum(1 for r in records if r.membership_id in voter_ids and r.status == "present")
    represented = sum(
        1 for r in records if r.membership_id in voter_ids and r.status == "represented"
    )
    guests = sum(1 for r in records if r.membership_id not in voter_ids and r.status == "present")
    return {
        "voters": len(voter_ids),
        "present": present,
        "represented": represented,
        "guests": guests,
        "quorum": services.quorum(meeting, len(voter_ids), present + represented),
        "proxies_allowed": meeting.kind.proxies_allowed,
        "editable": scope.can_edit and meeting.status in OPEN_FOR_ATTENDANCE,
        "rows": rows,
    }


class AttendanceInput(serializers.Serializer):
    membership = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    represented_by = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class AttendanceView(Base):
    def get(self, request, pk, **kwargs):
        require_members(self.scope)
        meeting = self.meeting(pk)
        return Response(attendance_data(meeting, self.scope))

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Eintrag anlegen oder ändern (Mitglied über ``membership``, Gast über ``name``)."""
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        if meeting.status not in OPEN_FOR_ATTENDANCE:
            raise ValidationError(
                {"detail": _("Die Anwesenheit lässt sich jetzt nicht mehr ändern.")}
            )
        ser = AttendanceInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
        if data.get("membership"):
            from members.models import Membership

            membership = get_object_or_404(
                Membership.objects.filter(organization=self.scope.org).select_related("person"),
                pk=data["membership"],
            )
            record_, _created = Attendance.objects.get_or_create(
                meeting=meeting,
                membership=membership,
                defaults={
                    "organization": self.scope.org,
                    "name": person_name(membership),
                    "status": data["status"],
                },
            )
            record_.voter = membership.pk in voter_ids
        else:
            name = (data.get("name") or "").strip()
            if not name:
                raise ValidationError({"name": _("Bitte einen Namen angeben.")})
            record_ = Attendance(organization=self.scope.org, meeting=meeting, name=name)
        record_.status = data["status"]
        record_.represented_by = None
        if record_.status == Attendance.Status.REPRESENTED:
            if not meeting.kind.proxies_allowed:
                raise ValidationError(
                    {"status": _("Bei dieser Art ist keine Vertretung mit Vollmacht vorgesehen.")}
                )
            holder = meeting.attendance.filter(
                pk=data.get("represented_by") or 0, status=Attendance.Status.PRESENT
            ).first()
            if (
                holder is None
                or holder.membership_id not in voter_ids
                or holder.pk == record_.pk
                or not record_.voter
            ):
                raise ValidationError(
                    {
                        "represented_by": _(
                            "Vertreten kann nur ein anwesendes stimmberechtigtes Mitglied."
                        )
                    }
                )
            record_.represented_by = holder
        record_.save()
        if record_.status != Attendance.Status.PRESENT:
            # Wer nicht mehr da ist, vertritt auch niemanden mehr
            record_.proxies.update(status=Attendance.Status.EXCUSED, represented_by=None)
        return Response(attendance_data(meeting, self.scope))


class AttendanceDetailView(Base):
    @transaction.atomic
    def delete(self, request, pk, entry, **kwargs):
        access.require_edit(self.scope)
        require_members(self.scope)
        meeting = self.meeting(pk, lock=True)
        if meeting.status not in OPEN_FOR_ATTENDANCE:
            raise ValidationError(
                {"detail": _("Die Anwesenheit lässt sich jetzt nicht mehr ändern.")}
            )
        record_ = get_object_or_404(meeting.attendance, pk=entry)
        record_.proxies.update(status=Attendance.Status.EXCUSED, represented_by=None)
        record_.delete()
        return Response(attendance_data(meeting, self.scope))


# --- Protokoll und Beschlüsse (Schritt V4) -------------------------------------------------

OPEN_FOR_MINUTES = (Meeting.Status.HELD, Meeting.Status.MINUTES)
MAX_RESOLUTIONS = 30


class ResolutionInput(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    kind = serializers.ChoiceField(choices=Resolution.Kind.choices, required=False)
    text = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    votes_yes = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    votes_no = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    votes_abstain = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    unanimous = serializers.BooleanField(required=False)
    result = serializers.ChoiceField(choices=Resolution.Result.choices, required=False)
    office = serializers.CharField(max_length=200, allow_blank=True, required=False)
    elected_name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    elected = serializers.IntegerField(min_value=1, allow_null=True, required=False)


class MinutesItemInput(serializers.Serializer):
    id = serializers.IntegerField()
    minutes = serializers.CharField(max_length=50000, allow_blank=True, required=False)
    resolutions = ResolutionInput(many=True, max_length=MAX_RESOLUTIONS, required=False)


class MinutesInput(serializers.Serializer):
    version = serializers.IntegerField()
    chair = serializers.CharField(max_length=200, allow_blank=True, required=False)
    minute_taker = serializers.CharField(max_length=200, allow_blank=True, required=False)
    items = MinutesItemInput(many=True, max_length=MAX_AGENDA)


def _resolution(scope, meeting, item, entry, existing) -> Resolution:
    r = existing.get(entry.get("id")) if entry.get("id") else None
    if r is None:
        r = Resolution(organization=scope.org, meeting=meeting, agenda_item=item)
    r.kind = entry.get("kind", r.kind or Resolution.Kind.RESOLUTION)
    r.text = (entry.get("text") or "").strip()
    r.office = (entry.get("office") or "").strip()
    r.elected_name = (entry.get("elected_name") or "").strip()
    r.elected = None
    if entry.get("elected"):
        from members.models import Membership

        r.elected = get_object_or_404(
            Membership.objects.filter(organization=scope.org).select_related("person"),
            pk=entry["elected"],
        )
        if not r.elected_name:
            r.elected_name = person_name(r.elected)
    if r.kind == Resolution.Kind.ELECTION:
        if not r.office or not r.elected_name:
            raise ValidationError(
                {"resolutions": _("Bei einer Wahl bitte Amt und gewählte Person angeben.")}
            )
        if not r.text:
            r.text = _("Wahl: {office}").format(office=r.office)
    elif not r.text:
        raise ValidationError({"resolutions": _("Jeder Beschluss braucht einen Text.")})
    r.unanimous = bool(entry.get("unanimous"))
    for field in ("votes_yes", "votes_no", "votes_abstain"):
        setattr(r, field, None if r.unanimous else entry.get(field))
    r.result = entry.get("result", r.result or Resolution.Result.ACCEPTED)
    if r.unanimous:
        r.result = Resolution.Result.ACCEPTED
    return r


class MinutesView(Base):
    """Protokoll als Ganzes speichern: Text je TOP, Beschlüsse und Wahlen."""

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        meeting = self.meeting(pk, lock=True)
        ser = MinutesInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data["version"] != meeting.version:
            raise conflict()
        if meeting.status not in OPEN_FOR_MINUTES:
            raise ValidationError({"detail": _("Das Protokoll lässt sich jetzt nicht ändern.")})
        before = snapshot(meeting)
        items = {a.pk: a for a in meeting.agenda.all()}
        existing = {r.pk: r for r in meeting.resolutions.all()}
        keep = set()
        for entry in data["items"]:
            item = items.get(entry["id"])
            if item is None:
                raise ValidationError({"items": _("Unbekannter Tagesordnungspunkt.")})
            if "minutes" in entry:
                item.minutes = entry["minutes"]
                item.save(update_fields=["minutes"])
            if "resolutions" not in entry:
                keep.update(r.pk for r in existing.values() if r.agenda_item_id == item.pk)
                continue
            for position, raw in enumerate(entry["resolutions"], start=1):
                r = _resolution(self.scope, meeting, item, raw, existing)
                if r.pk and r.agenda_item_id != item.pk:
                    raise ValidationError({"resolutions": _("Unbekannter Beschluss.")})
                r.position = position
                r.save()
                keep.add(r.pk)
        touched = {e["id"] for e in data["items"]}
        keep.update(r.pk for r in existing.values() if r.agenda_item_id not in touched)
        meeting.resolutions.exclude(pk__in=keep).delete()
        for field in ("chair", "minute_taker"):
            if field in data:
                setattr(meeting, field, data[field].strip())
        meeting.status = Meeting.Status.MINUTES
        meeting.version += 1
        meeting.save()
        changes = diff(before, snapshot(meeting))
        changes[_("Protokoll")] = [None, _("bearbeitet")]
        record(self.scope.org, request.user, "update", meeting, changes)
        return Response(meeting_data(meeting, self.scope, full=True))
