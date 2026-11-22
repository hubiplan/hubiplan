"""Verwaltung der API-Zugänge in HUBIplan: Einstellungen › API-Zugänge (docs/api.md).

Nur mit dem Zusatzrecht „API-Zugänge verwalten“ und eingeschaltetem Modul. Der Schlüssel
steht genau einmal in der Antwort auf das Anlegen bzw. auf „Neuen Schlüssel erzeugen“.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import API_MANAGE
from accounts import step_up
from audit.log import diff, record, snapshot
from core.api_base import OrgScopedMixin

from . import notify
from . import scopes as sc
from .auth import MODULE
from .models import (
    DEFAULT_LIFETIME,
    IDLE_LIFETIME,
    MAX_LIFETIME,
    MAX_PER_UNIT,
    ROTATE_OVERLAP,
    ApiAccess,
    parse_networks,
)
from .views import ACCESS_LIMIT

PATH = "/api/partner/v1/"


class _Base(OrgScopedMixin, APIView):
    read_permission = API_MANAGE
    write_permission = API_MANAGE
    allowed_org_types = ("federation", "club")

    def initial(self, request, *args, **kwargs):
        if not settings.PARTNER_API_ENABLED:
            raise NotFound()
        super().initial(request, *args, **kwargs)
        from access.modules import module_on

        if not module_on(self.org, MODULE):
            raise NotFound()

    def units(self):
        from organizations.models import Department
        from website.services import in_tree_order

        return in_tree_order(Department.objects.filter(organization=self.org, is_active=True))

    def access(self, pk: int) -> ApiAccess:
        return get_object_or_404(
            ApiAccess.objects.select_related("unit", "created_by"), organization=self.org, pk=pk
        )


class ScopeChoiceSerializer(serializers.Serializer):
    scope = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    unit_ok = serializers.BooleanField()
    needs = serializers.CharField(allow_blank=True)


class UnitChoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ApiAccessSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    purpose = serializers.CharField(allow_blank=True)
    recipient = serializers.CharField(allow_blank=True)
    scopes = serializers.ListField(child=serializers.CharField())
    unit = UnitChoiceSerializer(allow_null=True)
    key_hint = serializers.CharField()
    key_created_at = serializers.DateTimeField()
    previous_until = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    allowed_networks = serializers.ListField(child=serializers.CharField())
    embeddable = serializers.BooleanField()
    state = serializers.CharField(help_text="active, idle oder expired")
    idle_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField(allow_blank=True)
    last_used_at = serializers.DateTimeField(allow_null=True)
    last_used_ip = serializers.CharField(allow_blank=True)
    request_count = serializers.IntegerField()


class ApiAccessListSerializer(serializers.Serializer):
    address = serializers.CharField()
    docs = serializers.CharField()
    requests_per_hour = serializers.IntegerField()
    max_days = serializers.IntegerField()
    idle_days = serializers.IntegerField()
    overlap_days = serializers.IntegerField()
    scopes = ScopeChoiceSerializer(many=True)
    units = UnitChoiceSerializer(many=True)
    accesses = ApiAccessSerializer(many=True)


class ApiAccessCreatedSerializer(ApiAccessSerializer):
    key = serializers.CharField()


class ApiAccessInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    purpose = serializers.CharField(max_length=300, allow_blank=True, required=False)
    recipient = serializers.CharField(max_length=200, allow_blank=True, required=False)
    scopes = serializers.ListField(child=serializers.CharField(max_length=40), max_length=40)
    unit = serializers.IntegerField(allow_null=True, required=False)
    expires_at = serializers.DateField()
    allowed_networks = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, max_length=40
    )
    embeddable = serializers.BooleanField(required=False)


def _dump(access: ApiAccess) -> dict:
    now = timezone.now()
    creator = access.created_by
    previous = access.previous_until
    return {
        "id": access.pk,
        "name": access.name,
        "purpose": access.purpose,
        "recipient": access.recipient,
        "scopes": list(access.scopes or []),
        "unit": {"id": access.unit_id, "name": access.unit.name} if access.unit_id else None,
        "key_hint": access.key_hint,
        "key_created_at": access.key_created_at,
        "previous_until": previous if previous and previous > now else None,
        "expires_at": access.expires_at,
        "allowed_networks": list(access.allowed_networks or []),
        "embeddable": access.embeddable,
        "state": access.state,
        "idle_at": access.idle_since + IDLE_LIFETIME,
        "created_at": access.created_at,
        "created_by": (creator.get_full_name() or creator.email) if creator else "",
        "last_used_at": access.last_used_at,
        "last_used_ip": access.last_used_ip,
        "request_count": access.request_count,
    }


def _end_of(day: datetime.date) -> datetime.datetime:
    """Gültig bis zum Ende dieses Tages (Ortszeit)."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(23, 59, 59)))


class _Writer(_Base):
    def cleaned(self, request, instance: ApiAccess | None = None) -> dict:
        ser = ApiAccessInputSerializer(data=request.data, partial=instance is not None)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        errors: dict[str, str] = {}
        unit = instance.unit if instance is not None else None
        if "unit" in data:
            unit_id = data.pop("unit")
            unit = None
            if unit_id is not None:
                unit = next((u for u in self.units() if u.pk == unit_id), None)
                if unit is None:
                    errors["unit"] = _("Diese Untereinheit gibt es hier nicht.")
            data["unit"] = unit
        if "scopes" in data:
            wanted = data["scopes"]
            data["scopes"] = sc.clean(wanted, self.org, unit)
            if not data["scopes"]:
                errors["scopes"] = _("Bitte mindestens einen Bereich wählen.")
        elif instance is not None and "unit" in data:
            data["scopes"] = sc.clean(instance.scopes or [], self.org, unit)
            if not data["scopes"]:
                errors["scopes"] = _("Für eine Untereinheit bleibt keiner der Bereiche übrig.")
        if "expires_at" in data:
            until = _end_of(data["expires_at"])
            now = timezone.now()
            if until <= now:
                errors["expires_at"] = _("Das Datum muss in der Zukunft liegen.")
            elif until > now + MAX_LIFETIME:
                errors["expires_at"] = _("Höchstens ein Jahr; danach lässt sich verlängern.")
            data["expires_at"] = until
        if "allowed_networks" in data:
            try:
                data["allowed_networks"] = parse_networks(data["allowed_networks"])
            except ValueError:
                errors["allowed_networks"] = _(
                    "Bitte Adressen oder Netze eintragen, zum Beispiel 203.0.113.7 oder "
                    "203.0.113.0/24, höchstens 20."
                )
        scopes_now = data.get("scopes", instance.scopes if instance is not None else [])
        embeddable = data.get("embeddable", instance.embeddable if instance is not None else False)
        if embeddable and {sc.EVENTS_MEMBERS, sc.STATISTICS_READ} & set(scopes_now or []):
            errors["embeddable"] = _(
                "Aus fremden Webseiten aufrufbar geht nur ohne Mitgliedertermine und ohne "
                "Mitgliederzahlen: Der Schlüssel steht dann im Quelltext der Webseite."
            )
        if errors:
            raise serializers.ValidationError(errors)
        return data


class ApiAccessListView(_Writer):
    """GET: Zugänge der Einheit mit Auswahl der Bereiche; POST: neuer Zugang (Schlüssel einmal)."""

    @extend_schema(responses=ApiAccessListSerializer)
    def get(self, request, org_id: int):
        base = request.build_absolute_uri(PATH)
        data = {
            "address": base,
            "docs": f"{base}openapi.json",
            "requests_per_hour": ACCESS_LIMIT,
            "max_days": DEFAULT_LIFETIME.days,
            "idle_days": IDLE_LIFETIME.days,
            "overlap_days": ROTATE_OVERLAP.days,
            "scopes": [
                {
                    "scope": s.code,
                    "label": _(s.label),
                    "description": _(s.description),
                    "unit_ok": s.unit_ok,
                    "needs": s.needs,
                }
                for s in sc.available(self.org)
            ],
            "units": [{"id": u.pk, "name": u.name} for u in self.units()],
            "accesses": [
                _dump(a)
                for a in ApiAccess.objects.filter(organization=self.org).select_related(
                    "unit", "created_by"
                )
            ],
        }
        return Response(ApiAccessListSerializer(data).data)

    @extend_schema(request=ApiAccessInputSerializer, responses={201: ApiAccessCreatedSerializer})
    @transaction.atomic
    def post(self, request, org_id: int):
        # Ein neuer Schlüssel gibt Daten nach außen: frischer zweiter Faktor
        step_up.require(request)
        if ApiAccess.objects.filter(organization=self.org).count() >= MAX_PER_UNIT:
            raise serializers.ValidationError(
                {"detail": _("Mehr API-Zugänge sind je Einheit nicht möglich.")}
            )
        data = self.cleaned(request)
        access = ApiAccess(
            organization=self.org,
            unit=data.get("unit"),
            name=data["name"].strip(),
            purpose=data.get("purpose", "").strip(),
            recipient=data.get("recipient", "").strip(),
            scopes=data["scopes"],
            expires_at=data["expires_at"],
            allowed_networks=data.get("allowed_networks", []),
            embeddable=data.get("embeddable", False),
            created_by=request.user,
        )
        key = access.issue()
        access.save()
        record(self.org, request.user, "create", access, diff({}, snapshot(access)))
        notify.created(access, request.user)
        return Response(ApiAccessCreatedSerializer({**_dump(access), "key": key}).data, status=201)


class ApiAccessDetailView(_Writer):
    """PATCH: ändern oder verlängern; DELETE: löschen (der Schlüssel gilt sofort nicht mehr)."""

    @extend_schema(request=ApiAccessInputSerializer, responses=ApiAccessSerializer)
    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        access = self.access(pk)
        data = self.cleaned(request, access)
        before = snapshot(access)
        for field in ("name", "purpose", "recipient"):
            if field in data:
                setattr(access, field, data[field].strip())
        for field in ("unit", "scopes", "allowed_networks", "embeddable"):
            if field in data:
                setattr(access, field, data[field])
        if "expires_at" in data and data["expires_at"] != access.expires_at:
            access.expires_at = data["expires_at"]
            # Verlängert: vor dem neuen Ablauf wieder erinnern
            access.reminded_at = None
        access.save()
        changes = diff(before, snapshot(access))
        if changes:
            record(self.org, request.user, "update", access, changes)
        return Response(ApiAccessSerializer(_dump(access)).data)

    @extend_schema(responses={204: None})
    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        access = self.access(pk)
        record(self.org, request.user, "delete", access, diff(snapshot(access), {}))
        access.delete()
        return Response(status=204)


class ApiAccessRotateView(_Base):
    """POST: neuer Schlüssel; der bisherige gilt noch sieben Tage (Wechsel ohne Ausfall)."""

    @extend_schema(request=None, responses=ApiAccessCreatedSerializer)
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        step_up.require(request)
        access = self.access(pk)
        key = access.issue()
        access.save()
        record(
            self.org,
            request.user,
            "update",
            access,
            {"Schlüssel": [None, "neu erzeugt, der bisherige gilt noch sieben Tage"]},
        )
        notify.rotated(access, request.user)
        return Response(ApiAccessCreatedSerializer({**_dump(access), "key": key}).data)


class ApiAccessResumeView(_Base):
    """POST: ruhenden Zugang wieder einschalten (die Frist ohne Nutzung beginnt neu)."""

    @extend_schema(request=None, responses=ApiAccessSerializer)
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        step_up.require(request)
        access = self.access(pk)
        if access.state == "idle":
            access.active_since = timezone.now()
            access.save(update_fields=["active_since"])
            record(
                self.org,
                request.user,
                "update",
                access,
                {"Zustand": ["ruht", "wieder eingeschaltet"]},
            )
        return Response(ApiAccessSerializer(_dump(access)).data)
