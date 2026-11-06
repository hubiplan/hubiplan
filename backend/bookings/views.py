import datetime

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import access, services
from .models import Booking, BookingException, BookingSlot
from .rules import rules_of


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def booking(self, pk, *, lock=False):
        qs = Booking.objects.filter(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            item__in=access.items(self.scope),
        ).select_related("item")
        if lock:
            qs = qs.select_for_update()
        return get_object_or_404(qs, pk=pk)

    def data(self, booking):
        return booking_data(booking, self.scope, self.request.user)


def expected(booking, value):
    if type(value) is not int or value != booking.version:
        exc = APIException(_("Die Buchung wurde inzwischen geändert. Bitte neu laden."))
        exc.status_code = 409
        raise exc


def item_data(item, scope):
    rules = rules_of(item)
    return {
        "id": item.pk,
        "kind": item.kind,
        "inventory_number": item.inventory_number,
        "title": item.title,
        "facility": item.facility_id,
        "facility_type": item.facility_type,
        "condition": item.condition,
        "rules": rules,
        "can_book": access.can_book(scope, item),
        "can_manage": access.can_manage(scope, item),
    }


def booking_data(booking, scope, user):
    details = access.can_see_details(scope, booking, user)
    manage = access.can_manage(scope, booking.item)
    return {
        "id": booking.pk,
        "item": booking.item_id,
        "item_title": booking.item.title,
        "title": booking.title if details else _("Belegt"),
        "details": details,
        "note": booking.note if manage or booking.booked_by_id == user.pk else "",
        "starts_at": booking.starts_at,
        "ends_at": booking.ends_at,
        "all_day": booking.all_day,
        "repeat": booking.repeat,
        "repeat_interval": booking.repeat_interval,
        "repeat_until": booking.repeat_until,
        "status": booking.status,
        "visibility": booking.visibility,
        "contact": booking.contact if manage else {},
        "event": booking.event_id if details else None,
        "event_title": booking.event.title if details and booking.event_id else "",
        "competition": booking.competition_id if details else None,
        "competition_title": booking.competition.title
        if details and booking.competition_id
        else "",
        "needs_review": booking.needs_review,
        "own": booking.booked_by_id == user.pk,
        "booked_by": str(booking.booked_by) if manage and booking.booked_by_id else "",
        "can_manage": manage,
        "can_cancel": manage or booking.booked_by_id == user.pk,
        "version": booking.version,
        "loan": booking.item.kind == "material" and not booking.is_series,
        "handed_out_at": booking.handed_out_at,
        "handed_out_by": str(booking.handed_out_by) if manage and booking.handed_out_by_id else "",
        "returned_at": booking.returned_at,
        "returned_by": str(booking.returned_by) if manage and booking.returned_by_id else "",
        "exceptions": [
            e.isoformat()
            for e in booking.exceptions.order_by("original_start").values_list(
                "original_start", flat=True
            )
        ],
    }


class ContactInput(serializers.Serializer):
    name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    email = serializers.EmailField(allow_blank=True, required=False)
    phone = serializers.CharField(max_length=50, allow_blank=True, required=False)


class BookingInput(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    item = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    all_day = serializers.BooleanField(required=False, default=False)
    repeat = serializers.ChoiceField(choices=Booking.Repeat.choices, required=False, default="none")
    repeat_interval = serializers.IntegerField(min_value=1, max_value=52, required=False, default=1)
    repeat_until = serializers.DateField(required=False, allow_null=True)
    visibility = serializers.ChoiceField(
        choices=Booking.Visibility.choices, required=False, default="members"
    )
    contact = ContactInput(required=False)
    event = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    # Nur ein Vorkommen einer Terminreihe buchen (aus dem Material-Bedarf „Nur dieser Termin“)
    occurrence = serializers.DateTimeField(required=False)
    competition = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, data):
        scope, user = self.context["scope"], self.context["user"]
        booking = self.context.get("booking")
        item = access.items(scope).filter(pk=data["item"]).first()
        if item is None:
            raise ValidationError({"item": _("Bitte ein Objekt mit Buchungskalender wählen.")})
        access.require_book(scope, item)
        manage = access.can_manage(scope, item)
        data["item"] = item
        if data.get("event"):
            from materials.access import events

            event = events(user, scope).filter(pk=data["event"]).first()
            if event is None:
                raise ValidationError({"event": _("Termin nicht verfügbar.")})
            data["event"] = event
            data.setdefault("title", event.title)
            if data.get("occurrence"):
                data["event"] = None
                data.update(occurrence_times(event, data["occurrence"]))
        elif "event" in data:
            data["event"] = None
        if data.get("competition"):
            from competitions.models import Competition

            competition = (
                Competition.objects.filter(organization=scope.org, pk=data["competition"]).first()
                if {"competitions.view", "competitions.edit"} & scope.permissions
                else None
            )
            if competition is None:
                raise ValidationError({"competition": _("Wettbewerb nicht verfügbar.")})
            data["competition"] = competition
            data.setdefault("title", competition.title)
        elif "competition" in data:
            data["competition"] = None
        if not (data.get("title") or (booking and booking.title)):
            raise ValidationError({"title": _("Bitte einen Zweck angeben.")})
        if "contact" in data and not manage:
            raise PermissionDenied()
        target = booking or Booking()
        for key in ("starts_at", "ends_at", "all_day", "repeat", "repeat_interval", "repeat_until"):
            if key in data:
                setattr(target, key, data[key])
        if data.get("event"):
            services.copy_times(target, data["event"])
        elif data.get("competition"):
            services.competition_times(target, data["competition"])
        if not target.starts_at or not target.ends_at:
            raise ValidationError({"starts_at": _("Bitte Beginn und Ende angeben.")})
        if target.all_day:
            # Ganztägig: von 0:00 des ersten bis 0:00 nach dem letzten Tag (deutsche Zeit)
            start = timezone.localtime(target.starts_at, services.BERLIN).date()
            end = timezone.localtime(target.ends_at, services.BERLIN).date()
            if not data.get("event"):
                end = max(end, start) + datetime.timedelta(days=1)
            target.starts_at = datetime.datetime.combine(start, datetime.time(), services.BERLIN)
            target.ends_at = datetime.datetime.combine(end, datetime.time(), services.BERLIN)
        if target.ends_at <= target.starts_at:
            raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})
        if target.ends_at - target.starts_at > datetime.timedelta(days=60):
            raise ValidationError({"ends_at": _("Eine Buchung dauert höchstens 60 Tage.")})
        if (
            target.repeat != "none"
            and target.repeat_until
            and target.repeat_until < timezone.localdate(target.starts_at)
        ):
            raise ValidationError({"repeat_until": _("Das Ende der Serie liegt vor dem Beginn.")})
        if not manage:
            now = timezone.now()
            horizon = now + datetime.timedelta(days=rules_of(item)["horizon_days"])
            if target.ends_at < now:
                raise ValidationError(
                    {"starts_at": _("Vergangene Zeiten kann nur die Verwaltung eintragen.")}
                )
            if target.starts_at > horizon:
                raise ValidationError(
                    {"starts_at": _("So weit im Voraus ist dieses Objekt nicht buchbar.")}
                )
        for key in ("starts_at", "ends_at", "all_day", "repeat", "repeat_interval", "repeat_until"):
            data[key] = getattr(target, key)
        data.pop("occurrence", None)
        return data


def occurrence_times(event, original):
    from events.recurrence import occurrences

    for occ in occurrences(
        [event], original - datetime.timedelta(days=1), original + datetime.timedelta(days=1)
    ):
        if occ.original_start == original and not occ.is_cancelled:
            # Ganztägig: das Tagesende ergänzt die Prüfung unten wie bei einer Eingabe
            return {
                "starts_at": occ.starts_at,
                "ends_at": occ.ends_at,
                "all_day": event.all_day,
                "repeat": "none",
                "repeat_until": None,
            }
    raise ValidationError({"occurrence": _("Dieser Termin findet nicht statt.")})


def window(request):
    field = serializers.DateField()
    today = timezone.localdate()
    start = field.run_validation(request.query_params.get("start") or today.isoformat())
    end = field.run_validation(
        request.query_params.get("end") or (start + datetime.timedelta(days=7)).isoformat()
    )
    if end <= start or (end - start).days > 400:
        raise ValidationError(_("Bitte einen Zeitraum bis 400 Tage wählen."))
    return (
        datetime.datetime.combine(start, datetime.time(), services.BERLIN),
        datetime.datetime.combine(end, datetime.time(), services.BERLIN),
    )


class ItemsView(Base):
    def get(self, request, **kwargs):
        rows = [item_data(i, self.scope) for i in access.items(self.scope).order_by("pk")]
        return Response(
            {"items": rows, "can_manage_all": "bookings.edit" in self.scope.permissions}
        )


class ListView(Base):
    def get(self, request, **kwargs):
        start, end = window(request)
        visible = access.items(self.scope)
        if request.query_params.get("item"):
            item = get_object_or_404(visible, pk=request.query_params["item"])
            # Ein Gebäude zeigt auch Buchungen seiner Bereiche, ein Bereich die des Gebäudes
            shown = {item.pk, *visible.filter(facility_id=item.pk).values_list("pk", flat=True)}
            if item.facility_id:
                shown.add(item.facility_id)
            visible = visible.filter(pk__in=shown)
        slots = (
            BookingSlot.objects.filter(
                organization=self.scope.org,
                booking__item__in=visible,
                resource_id=F("booking__item_id"),
                starts_at__lt=end,
                ends_at__gt=start,
            )
            .select_related("booking__item", "booking__booked_by", "booking__event")
            .order_by("starts_at", "pk")
        )
        if request.query_params.get("mine") == "1":
            slots = slots.filter(booking__booked_by=request.user)
        rows = []
        cache = {}
        for slot in slots[:2000]:
            booking = slot.booking
            if booking.pk not in cache:
                cache[booking.pk] = self.data(booking)
            data = cache[booking.pk]
            rows.append(
                {
                    "booking": booking.pk,
                    "item": booking.item_id,
                    "item_title": data["item_title"],
                    "title": data["title"],
                    "starts_at": slot.starts_at,
                    "ends_at": slot.ends_at,
                    "original_start": slot.original_start,
                    "all_day": booking.all_day,
                    "status": booking.status,
                    "series": booking.is_series,
                    "own": data["own"],
                    "needs_review": booking.needs_review,
                }
            )
        pending = []
        if any(access.can_manage(self.scope, i) for i in visible):
            pending = [
                self.data(b)
                for b in Booking.objects.filter(
                    organization=self.scope.org,
                    department_id=self.scope.department_id,
                    item__in=visible,
                    status=Booking.Status.REQUESTED,
                ).select_related("item", "booked_by", "event", "competition")
                if access.can_manage(self.scope, b.item)
            ]
        return Response({"occurrences": rows, "requests": pending})

    @transaction.atomic
    def post(self, request, **kwargs):
        form = BookingInput(data=request.data, context={"scope": self.scope, "user": request.user})
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        values.pop("version", None)
        item = values["item"]
        manage = access.can_manage(self.scope, item)
        confirmed = manage or not rules_of(item)["approval"]
        booking = Booking.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            booked_by=request.user,
            status=Booking.Status.CONFIRMED if confirmed else Booking.Status.REQUESTED,
            decided_by=request.user if confirmed else None,
            decided_at=timezone.now() if confirmed else None,
            **{**values, "contact": dict(values.get("contact") or {})},
        )
        services.rebuild(booking)
        return Response(self.data(booking), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        booking = self.booking(pk)
        if not access.can_see_details(self.scope, booking, request.user):
            raise PermissionDenied()
        return Response(self.data(booking))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        booking = self.booking(pk, lock=True)
        manage = access.can_manage(self.scope, booking.item)
        if not manage and booking.booked_by_id != request.user.pk:
            raise PermissionDenied()
        expected(booking, request.data.get("version"))
        if booking.status in (Booking.Status.CANCELLED, Booking.Status.REJECTED):
            raise ValidationError(_("Diese Buchung ist nicht mehr aktiv."))
        form = BookingInput(
            data={"item": booking.item_id, **request.data},
            partial=True,
            context={"scope": self.scope, "user": request.user, "booking": booking},
        )
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        values.pop("version", None)
        if values.pop("item") != booking.item:
            raise ValidationError({"item": _("Das Objekt einer Buchung lässt sich nicht ändern.")})
        if "contact" in values:
            values["contact"] = dict(values["contact"])
        for key, value in values.items():
            setattr(booking, key, value)
        # Geänderte Zeiten einer Anfrage oder ohne Freigaberecht: wieder zur Freigabe
        if not manage and rules_of(booking.item)["approval"]:
            booking.status = Booking.Status.REQUESTED
        booking.needs_review = False
        booking.version += 1
        booking.save()
        services.rebuild(booking)
        return Response(self.data(booking))


class DecisionView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        booking = self.booking(pk, lock=True)
        expected(booking, request.data.get("version"))
        action = request.data.get("action")
        manage = access.can_manage(self.scope, booking.item)
        if action == "cancel":
            if not manage and booking.booked_by_id != request.user.pk:
                raise PermissionDenied()
            booking.status = Booking.Status.CANCELLED
        elif action in ("confirm", "reject"):
            if not manage:
                raise PermissionDenied()
            if booking.status not in (Booking.Status.REQUESTED, Booking.Status.CONFIRMED):
                raise ValidationError(_("Diese Buchung ist nicht mehr aktiv."))
            booking.status = (
                Booking.Status.CONFIRMED if action == "confirm" else Booking.Status.REJECTED
            )
            booking.decided_by = request.user
            booking.decided_at = timezone.now()
        else:
            raise ValidationError(_("Ungültige Auswahl."))
        booking.needs_review = False
        booking.version += 1
        booking.save()
        services.rebuild(booking)
        return Response(self.data(booking))


class HandoverInput(serializers.Serializer):
    version = serializers.IntegerField()
    action = serializers.ChoiceField(choices=["out", "return", "undo"])
    # Zustand nur übernehmen, wenn ausdrücklich angekreuzt (keine Automatik)
    update_item = serializers.BooleanField(required=False, default=False)
    condition = serializers.ChoiceField(
        choices=["ready", "limited", "defective", "retired"], required=False
    )
    condition_note = serializers.CharField(max_length=500, allow_blank=True, required=False)


class HandoverView(Base):
    """Ausleihe von Material: Ausgabe und Rückgabe bestätigen."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        booking = self.booking(pk, lock=True)
        if not access.can_manage(self.scope, booking.item):
            raise PermissionDenied()
        expected(booking, request.data.get("version"))
        form = HandoverInput(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if booking.item.kind != "material" or booking.is_series:
            raise ValidationError(_("Ausgabe und Rückgabe gibt es nur bei einmaligen Ausleihen."))
        if booking.status != Booking.Status.CONFIRMED:
            raise ValidationError(_("Diese Buchung ist nicht bestätigt."))
        now = timezone.now()
        if data["action"] == "out":
            if booking.handed_out_at:
                raise ValidationError(_("Das Material ist schon ausgegeben."))
            booking.handed_out_at, booking.handed_out_by = now, request.user
        elif data["action"] == "return":
            if not booking.handed_out_at or booking.returned_at:
                raise ValidationError(_("Das Material ist nicht ausgegeben."))
            booking.returned_at, booking.returned_by = now, request.user
            if data["update_item"]:
                self.update_item(booking.item, data)
        elif booking.returned_at:
            booking.returned_at = booking.returned_by = None
        else:
            booking.handed_out_at = booking.handed_out_by = None
        booking.version += 1
        booking.save()
        return Response(self.data(booking))

    def update_item(self, item, data):
        from materials import services as material_services
        from materials.models import MaterialItem

        if not {"condition", "condition_note"} & set(data):
            return
        if "material.edit" not in self.scope.permissions:
            raise PermissionDenied()
        item = MaterialItem.objects.select_for_update().get(pk=item.pk)
        before = material_services.snapshot(item)
        if "condition" in data:
            item.condition = data["condition"]
        if "condition_note" in data:
            item.condition_note = data["condition_note"]
        material_services.changed(item, self.request.user, before, "update")


class SkipView(Base):
    """Ein einzelnes Vorkommen einer Serienbuchung absagen oder wieder aufnehmen."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        booking = self.booking(pk, lock=True)
        if not access.can_manage(self.scope, booking.item) and (
            booking.booked_by_id != request.user.pk
        ):
            raise PermissionDenied()
        expected(booking, request.data.get("version"))
        if not booking.is_series:
            raise ValidationError(_("Nur bei Serien lässt sich ein einzelner Termin absagen."))
        original = serializers.DateTimeField().run_validation(request.data.get("original_start"))
        if request.data.get("restore") is True:
            booking.exceptions.filter(original_start=original).delete()
        else:
            if original not in {o for o, _b, _e in services.occurrences(booking)}:
                raise ValidationError(_("Dieses Vorkommen gehört nicht zur Serie."))
            BookingException.objects.get_or_create(
                organization=self.scope.org, booking=booking, original_start=original
            )
        booking.version += 1
        booking.save()
        services.rebuild(booking)
        return Response(self.data(booking))


class ChoicesView(Base):
    def get(self, request, **kwargs):
        query = request.query_params.get("q", "").casefold().strip()
        kind = request.query_params.get("kind")
        if kind == "event":
            from materials.access import events

            rows = [
                {"id": e.pk, "title": e.title, "starts_at": e.starts_at, "series": e.is_series}
                for e in events(request.user, self.scope)
                .filter(is_cancelled=False)
                .order_by("-starts_at")[:500]
            ]
        elif kind == "competition":
            from competitions.models import Competition

            if not {"competitions.view", "competitions.edit"} & self.scope.permissions:
                rows = []
            else:
                rows = [
                    {"id": c.pk, "title": c.title, "starts_at": c.date}
                    for c in Competition.objects.filter(organization=self.scope.org).order_by(
                        "-date"
                    )[:500]
                ]
        else:
            raise ValidationError(_("Ungültige Auswahl."))
        rows = [r for r in rows if query in r["title"].casefold()]
        return Response({"items": rows[:50], "more": len(rows) > 50})
