"""Anfragen von Mitgliedern im Mitgliederbereich (konzepte/infrastruktur.md, Schritt 5).

Mitglieder ohne Verwaltungsrecht sehen nur Objekte mit ``booking_rules.portal``, deren
belegte Zeiten (ohne Zweck fremder Buchungen) und ihre eigenen Anfragen. Eine Anfrage
blockiert nichts, bis die Verwaltung sie bestätigt; dann prüft die Datenbank Überschneidungen.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import services
from .models import Booking, BookingSlot
from .rules import rules_of

AREAS = {"material": "material", "facility": "infrastructure"}


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if not access.membership.current_period():
        raise NotFound()
    return access


def portal_items(org):
    from materials.models import MaterialItem

    modules = set(org.enabled_modules or [])
    if "bookings" not in modules:
        return MaterialItem.objects.none()
    kinds = [kind for kind, module in AREAS.items() if module in modules]
    return MaterialItem.objects.filter(
        organization=org,
        department__isnull=True,
        kind__in=kinds,
        deleted_at__isnull=True,
        booking_rules__enabled=True,
        booking_rules__portal=True,
    ).exclude(condition__in=["defective", "retired"])


def own_data(booking):
    return {
        "id": booking.pk,
        "item": booking.item_id,
        "item_title": booking.item.title,
        "title": booking.title,
        "note": booking.note,
        "starts_at": booking.starts_at,
        "ends_at": booking.ends_at,
        "all_day": booking.all_day,
        "status": booking.status,
        "version": booking.version,
    }


class PortalInput(serializers.Serializer):
    item = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=200)
    note = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    all_day = serializers.BooleanField(required=False, default=False)


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def own(self):
        return Booking.objects.filter(
            organization=self.org, department__isnull=True, booked_by=self.request.user
        ).select_related("item")


class ListView(Base):
    def get(self, request, **kwargs):
        field = serializers.DateField()
        start = field.run_validation(
            request.query_params.get("start") or timezone.localdate().isoformat()
        )
        begin = datetime.datetime.combine(start, datetime.time(), services.BERLIN)
        end = begin + datetime.timedelta(days=7)
        items = list(portal_items(self.org).order_by("pk"))
        busy = []
        for slot in (
            BookingSlot.objects.filter(
                resource__in=items, confirmed=True, starts_at__lt=end, ends_at__gt=begin
            )
            .select_related("booking")
            .order_by("starts_at")[:1000]
        ):
            mine = slot.booking.booked_by_id == request.user.pk
            busy.append(
                {
                    "item": slot.resource_id,
                    "title": slot.booking.title if mine else _("Belegt"),
                    "starts_at": slot.starts_at,
                    "ends_at": slot.ends_at,
                    "all_day": slot.booking.all_day,
                    "own": mine,
                }
            )
        recent = timezone.now() - datetime.timedelta(days=30)
        return Response(
            {
                "items": [
                    {
                        "id": i.pk,
                        "kind": i.kind,
                        "title": i.title,
                        "facility": i.facility_id,
                        "horizon_days": rules_of(i)["horizon_days"],
                    }
                    for i in items
                ],
                "occurrences": busy,
                "own": [
                    own_data(b)
                    for b in self.own().filter(ends_at__gte=recent).order_by("starts_at")[:100]
                ],
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        form = PortalInput(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        item = portal_items(self.org).filter(pk=data["item"]).first()
        if item is None:
            raise ValidationError({"item": _("Bitte ein Objekt mit Buchungskalender wählen.")})
        start, end = data["starts_at"], data["ends_at"]
        if data["all_day"]:
            first = timezone.localtime(start, services.BERLIN).date()
            last = max(timezone.localtime(end, services.BERLIN).date(), first)
            start = datetime.datetime.combine(first, datetime.time(), services.BERLIN)
            end = datetime.datetime.combine(
                last + datetime.timedelta(days=1), datetime.time(), services.BERLIN
            )
        now = timezone.now()
        if end <= start:
            raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})
        if end - start > datetime.timedelta(days=60):
            raise ValidationError({"ends_at": _("Eine Buchung dauert höchstens 60 Tage.")})
        if end < now:
            raise ValidationError(
                {"starts_at": _("Vergangene Zeiten kann nur die Verwaltung eintragen.")}
            )
        if start > now + datetime.timedelta(days=rules_of(item)["horizon_days"]):
            raise ValidationError(
                {"starts_at": _("So weit im Voraus ist dieses Objekt nicht buchbar.")}
            )
        if self.own().filter(status=Booking.Status.REQUESTED).count() >= 20:
            raise ValidationError(_("Du hast schon 20 offene Anfragen."))
        booking = Booking.objects.create(
            organization=self.org,
            item=item,
            title=data["title"],
            note=data["note"],
            starts_at=start,
            ends_at=end,
            all_day=data["all_day"],
            status=Booking.Status.REQUESTED,
            visibility=Booking.Visibility.MEMBERS,
            booked_by=request.user,
        )
        services.rebuild(booking)
        booking.item = item
        return Response(own_data(booking), status=201)


class CancelView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        booking = get_object_or_404(self.own().select_for_update(of=("self",)), pk=pk)
        if request.data.get("version") != booking.version:
            from .views import expected

            expected(booking, request.data.get("version"))
        if booking.status in (Booking.Status.REQUESTED, Booking.Status.CONFIRMED):
            booking.status = Booking.Status.CANCELLED
            booking.version += 1
            booking.save()
            services.rebuild(booking)
        return Response(own_data(booking))
