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

from . import notify, webhooks
from . import scopes as sc
from .auth import MODULE
from .docs_page import DOCS_URL
from .models import (
    DEFAULT_LIFETIME,
    IDLE_LIFETIME,
    LOG_KEEP,
    MAX_LIFETIME,
    MAX_PER_UNIT,
    ROTATE_OVERLAP,
    ApiAccess,
    ReadLog,
    new_hook_secret,
    parse_networks,
)
from .personal import MEMBER_FIELDS
from .views import ACCESS_LIMIT, WRITE_LIMIT

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
            ApiAccess.objects.select_related("unit", "created_by", "partner", "legal_confirmed_by"),
            organization=self.org,
            pk=pk,
        )

    def forget(self) -> None:
        """Merker „gibt es Benachrichtigungen?“ verwerfen, jetzt und nach dem Abschluss."""
        org_id = self.org.pk
        webhooks.forget_flags(org_id)
        transaction.on_commit(lambda: webhooks.forget_flags(org_id))

    def partners(self):
        """Aktive Geschäftspartner der Einheit als mögliche Empfänger."""
        from billing.models import BusinessPartner

        rows = BusinessPartner.objects.filter(organization=self.org, is_active=True)
        return sorted(rows, key=lambda p: (p.name or "").lower())


class ScopeChoiceSerializer(serializers.Serializer):
    scope = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    unit_ok = serializers.BooleanField()
    needs = serializers.CharField(allow_blank=True)
    personal = serializers.BooleanField()
    write = serializers.BooleanField()


class UnitChoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PartnerChoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    processor = serializers.BooleanField()


class HookEventChoiceSerializer(serializers.Serializer):
    event = serializers.CharField()
    label = serializers.CharField()
    scope = serializers.CharField()


class ReadLogSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    scope = serializers.CharField()
    count = serializers.IntegerField()


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
    write_count = serializers.IntegerField(help_text="schreibende Anfragen")
    last_write_at = serializers.DateTimeField(allow_null=True)
    writes = serializers.BooleanField(help_text="darf schreiben")
    partner = UnitChoiceSerializer(allow_null=True)
    legal_basis = serializers.CharField(
        allow_blank=True, help_text="processing, transfer oder leer"
    )
    legal_confirmed_at = serializers.DateTimeField(allow_null=True)
    legal_confirmed_by = serializers.CharField(allow_blank=True)
    third_country = serializers.BooleanField()
    member_fields = serializers.ListField(child=serializers.CharField())
    only_active = serializers.BooleanField()
    adults_only = serializers.BooleanField()
    report_level = serializers.CharField(help_text="a (nur Zahlen) oder b (namentlich)")
    personal = serializers.BooleanField(help_text="gibt Personendaten heraus")
    webhook_url = serializers.CharField(allow_blank=True)
    webhook_events = serializers.ListField(child=serializers.CharField())
    webhook_state = serializers.CharField(help_text="off, ok, failing oder paused")
    webhook_last_ok_at = serializers.DateTimeField(allow_null=True)
    webhook_last_error = serializers.CharField(allow_blank=True)
    records_read = serializers.IntegerField(help_text="Datensätze mit Personendaten, 90 Tage")
    reads = ReadLogSerializer(many=True, help_text="die letzten Abrufe von Personendaten")


class ApiAccessListSerializer(serializers.Serializer):
    address = serializers.CharField()
    docs = serializers.CharField(help_text="OpenAPI-Beschreibung (JSON)")
    docs_page = serializers.CharField(help_text="lesbare Beschreibung ohne Anmeldung")
    guide = serializers.CharField(help_text="ausführliche Anleitung (docs/api.md)")
    requests_per_hour = serializers.IntegerField()
    writes_per_hour = serializers.IntegerField()
    max_days = serializers.IntegerField()
    idle_days = serializers.IntegerField()
    overlap_days = serializers.IntegerField()
    scopes = ScopeChoiceSerializer(many=True)
    units = UnitChoiceSerializer(many=True)
    partners = PartnerChoiceSerializer(many=True)
    member_fields = serializers.ListField(child=serializers.CharField())
    webhook_events = HookEventChoiceSerializer(many=True)
    log_days = serializers.IntegerField()
    accesses = ApiAccessSerializer(many=True)


class ApiAccessCreatedSerializer(ApiAccessSerializer):
    key = serializers.CharField()
    webhook_secret = serializers.CharField(
        required=False, help_text="nur, wenn das Geheimnis gerade neu entstanden ist"
    )


class ApiAccessChangedSerializer(ApiAccessSerializer):
    webhook_secret = serializers.CharField(
        required=False, help_text="nur, wenn das Geheimnis gerade neu entstanden ist"
    )


class WebhookSecretSerializer(ApiAccessSerializer):
    webhook_secret = serializers.CharField()


class WebhookTestSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)


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
    partner = serializers.IntegerField(allow_null=True, required=False)
    legal_basis = serializers.ChoiceField(
        choices=["", "processing", "transfer"], allow_blank=True, required=False
    )
    legal_confirmed = serializers.BooleanField(
        required=False, help_text="„Ich bestätige die Rechtsgrundlage“"
    )
    third_country = serializers.BooleanField(required=False)
    member_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=list(MEMBER_FIELDS)), required=False, max_length=10
    )
    only_active = serializers.BooleanField(required=False)
    adults_only = serializers.BooleanField(required=False)
    report_level = serializers.ChoiceField(choices=["a", "b"], required=False)
    webhook_url = serializers.CharField(max_length=500, allow_blank=True, required=False)
    webhook_events = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=20
    )
    webhook_resume = serializers.BooleanField(
        required=False, help_text="ruhende Benachrichtigungen wieder einschalten"
    )


def _who(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


def _hook_state(access: ApiAccess) -> str:
    if not access.webhook_url:
        return "off"
    if access.webhook_paused_at:
        return "paused"
    return "failing" if access.webhook_failing_since else "ok"


def _reads(org) -> dict[int, dict]:
    """Je Zugang: Summe der gelesenen Datensätze und die letzten Abrufe."""
    out: dict[int, dict] = {}
    for log in ReadLog.objects.filter(organization=org).order_by("-at", "-pk")[:2000]:
        entry = out.setdefault(log.access_id, {"records": 0, "reads": []})
        entry["records"] += log.count
        if len(entry["reads"]) < 5:
            entry["reads"].append({"at": log.at, "scope": log.scope, "count": log.count})
    return out


def _dump(access: ApiAccess, reads: dict | None = None) -> dict:
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
        "created_by": _who(creator),
        "last_used_at": access.last_used_at,
        "last_used_ip": access.last_used_ip,
        "request_count": access.request_count,
        "write_count": access.write_count,
        "last_write_at": access.last_write_at,
        "writes": sc.writes(access.scopes),
        "partner": {"id": access.partner_id, "name": access.partner.name}
        if access.partner_id
        else None,
        "legal_basis": access.legal_basis,
        "legal_confirmed_at": access.legal_confirmed_at,
        "legal_confirmed_by": _who(access.legal_confirmed_by),
        "third_country": access.third_country,
        "member_fields": list(access.member_fields or []),
        "only_active": access.only_active,
        "adults_only": access.adults_only,
        "report_level": access.report_level,
        "personal": sc.personal(access.scopes, access.report_level),
        "webhook_url": access.webhook_url,
        "webhook_events": list(access.webhook_events or []),
        "webhook_state": _hook_state(access),
        "webhook_last_ok_at": access.webhook_last_ok_at,
        "webhook_last_error": access.webhook_last_error,
        "records_read": (reads or {}).get("records", 0),
        "reads": (reads or {}).get("reads", []),
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

        def now(field: str, default):
            if field in data:
                return data[field]
            return getattr(instance, field) if instance is not None else default

        scopes_now = now("scopes", [])
        internal = {sc.EVENTS_MEMBERS, sc.STATISTICS_READ, sc.REPORT_READ}
        personal = sc.personal(scopes_now, now("report_level", "a"))
        if now("embeddable", False) and (personal or internal & set(scopes_now or [])):
            errors["embeddable"] = _(
                "Aus fremden Webseiten aufrufbar geht nur ohne Mitgliedertermine, "
                "Mitgliederzahlen und Personendaten: Der Schlüssel steht dann im Quelltext der "
                "Webseite."
            )
        if now("embeddable", False) and sc.writes(scopes_now) and "embeddable" not in errors:
            errors["embeddable"] = _(
                "Aus fremden Webseiten aufrufbar geht nur ohne Schreiben: Der Schlüssel steht "
                "dann im Quelltext der Webseite."
            )
        before_scopes = set(instance.scopes or []) if instance is not None else set()
        data["_writes_new"] = bool(
            {s for s in scopes_now if sc.SCOPE_BY_CODE[s].write} - before_scopes
        )
        partner = instance.partner if instance is not None else None
        if "partner" in data:
            partner_id = data.pop("partner")
            partner = None
            if partner_id is not None:
                partner = next((p for p in self.partners() if p.pk == partner_id), None)
                if partner is None:
                    errors["partner"] = _("Diesen Geschäftspartner gibt es hier nicht.")
            data["partner"] = partner
        basis = now("legal_basis", "")
        before = (
            (instance.partner_id, instance.legal_basis, bool(instance.legal_confirmed_at))
            if instance is not None
            else (None, "", False)
        )
        # Die Bestätigung gilt für genau diesen Empfänger und diese Rechtsgrundlage
        same = (partner.pk if partner else None, basis) == before[:2]
        confirmed = bool(data.pop("legal_confirmed", False)) or (same and before[2])
        if personal:
            if partner is None and "partner" not in errors:
                errors["partner"] = _(
                    "Für Personendaten bitte den Empfänger aus den Geschäftspartnern wählen."
                )
            if not basis:
                errors["legal_basis"] = _("Für Personendaten bitte die Rechtsgrundlage wählen.")
            elif not confirmed:
                errors["legal_confirmed"] = _("Bitte die Rechtsgrundlage bestätigen.")
        data["_confirm"] = bool(partner and basis and confirmed) and not (same and before[2])
        data["_unconfirm"] = not (partner and basis and confirmed)
        data["_personal_new"] = personal and (
            instance is None
            or not sc.personal(instance.scopes, instance.report_level)
            or not same
            or bool(set(now("member_fields", [])) - set(instance.member_fields or []))
            or bool(
                {s for s in scopes_now if sc.SCOPE_BY_CODE[s].personal} - set(instance.scopes or [])
            )
            or (now("report_level", "a") == "b" and instance.report_level != "b")
        )
        if "member_fields" in data:
            data["member_fields"] = [f for f in MEMBER_FIELDS if f in set(data["member_fields"])]
        if "webhook_url" in data:
            try:
                data["webhook_url"] = webhooks.clean_url(data["webhook_url"])
            except ValueError:
                errors["webhook_url"] = _(
                    "Bitte eine Adresse mit https:// eintragen, ohne Benutzername und Passwort."
                )
        if "webhook_events" in data or "scopes" in data:
            data["webhook_events"] = webhooks.clean_events(now("webhook_events", []), scopes_now)
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def apply(self, request, access: ApiAccess, data: dict) -> str:
        """Felder der Stufe 2 übernehmen; liefert ein neu entstandenes Geheimnis ``hpw_…``."""
        from billing.models import BusinessPartner

        for field in (
            "partner",
            "legal_basis",
            "third_country",
            "member_fields",
            "only_active",
            "adults_only",
            "report_level",
            "webhook_events",
        ):
            if field in data:
                setattr(access, field, data[field])
        if data["_unconfirm"]:
            access.legal_confirmed_at = None
            access.legal_confirmed_by = None
        elif data["_confirm"]:
            access.legal_confirmed_at = timezone.now()
            access.legal_confirmed_by = request.user
        partner = access.partner
        processing = access.legal_basis == ApiAccess.LegalBasis.PROCESSING
        role = BusinessPartner.Role.PROCESSOR
        if data["_confirm"] and processing and role not in (partner.roles or []):
            # Steht damit im Verzeichnis der Verarbeitungstätigkeiten unter Auftragsverarbeiter
            old = list(partner.roles or [])
            partner.roles = [*old, role]
            partner.save(update_fields=["roles"])
            record(self.org, request.user, "update", partner, {"Rollen": [old, partner.roles]})
        secret = ""
        if "webhook_url" in data and data["webhook_url"] != access.webhook_url:
            access.webhook_url = data["webhook_url"]
            access.webhook_failing_since = None
            access.webhook_paused_at = None
            access.webhook_last_error = ""
            if access.webhook_url and not access.webhook_secret:
                secret = access.webhook_secret = new_hook_secret()
        if data.get("webhook_resume") and access.webhook_paused_at:
            access.webhook_paused_at = None
            access.webhook_failing_since = None
        return secret

    def sensitive(self, access: ApiAccess, data: dict) -> bool:
        """Änderungen, die mehr Daten nach außen geben, Filter lockern oder Laufzeit verlängern."""
        scopes_added = "scopes" in data and bool(set(data["scopes"]) - set(access.scopes or []))
        unit_changed = "unit" in data and (
            getattr(data["unit"], "pk", None) != access.unit_id
        )
        networks_changed = (
            "allowed_networks" in data and data["allowed_networks"] != (access.allowed_networks or [])
        )
        only_active_relaxed = "only_active" in data and access.only_active and not data["only_active"]
        adults_only_relaxed = "adults_only" in data and access.adults_only and not data["adults_only"]
        fields_added = "member_fields" in data and bool(
            set(data["member_fields"]) - set(access.member_fields or [])
        )
        expiry_extended = (
            "expires_at" in data
            and data["expires_at"] is not None
            and (access.expires_at is None or data["expires_at"] > access.expires_at)
        )
        return (
            data["_personal_new"]
            or data["_writes_new"]
            or scopes_added
            or unit_changed
            or networks_changed
            or only_active_relaxed
            or adults_only_relaxed
            or fields_added
            or expiry_extended
            or ("webhook_url" in data and data["webhook_url"] != access.webhook_url)
        )


class ApiAccessListView(_Writer):
    """GET: Zugänge der Einheit mit Auswahl der Bereiche; POST: neuer Zugang (Schlüssel einmal)."""

    @extend_schema(responses=ApiAccessListSerializer)
    def get(self, request, org_id: int):
        from billing.models import BusinessPartner

        base = request.build_absolute_uri(PATH)
        reads = _reads(self.org)
        data = {
            "address": base,
            "docs": f"{base}openapi.json",
            "docs_page": f"{base}docs/",
            "guide": DOCS_URL,
            "requests_per_hour": ACCESS_LIMIT,
            "writes_per_hour": WRITE_LIMIT,
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
                    "personal": s.personal,
                    "write": s.write,
                }
                for s in sc.available(self.org)
            ],
            "units": [{"id": u.pk, "name": u.name} for u in self.units()],
            "partners": [
                {
                    "id": p.pk,
                    "name": p.name,
                    "processor": BusinessPartner.Role.PROCESSOR in (p.roles or []),
                }
                for p in self.partners()
            ],
            "member_fields": list(MEMBER_FIELDS),
            "webhook_events": [
                {"event": e.code, "label": _(e.label), "scope": e.scope} for e in webhooks.EVENTS
            ],
            "log_days": LOG_KEEP.days,
            "accesses": [
                _dump(a, reads.get(a.pk))
                for a in ApiAccess.objects.filter(organization=self.org).select_related(
                    "unit", "created_by", "partner", "legal_confirmed_by"
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
        secret = self.apply(request, access, data)
        access.save()
        self.forget()
        record(self.org, request.user, "create", access, diff({}, snapshot(access)))
        notify.created(access, request.user)
        if data["_personal_new"]:
            notify.personal(access, request.user)
        if data["_writes_new"]:
            notify.writes(access, request.user)
        out = {**_dump(access), "key": key}
        if secret:
            out["webhook_secret"] = secret
        return Response(ApiAccessCreatedSerializer(out).data, status=201)


class ApiAccessDetailView(_Writer):
    """PATCH: ändern oder verlängern; DELETE: löschen (der Schlüssel gilt sofort nicht mehr)."""

    @extend_schema(request=ApiAccessInputSerializer, responses=ApiAccessChangedSerializer)
    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        access = self.access(pk)
        data = self.cleaned(request, access)
        if self.sensitive(access, data):
            # Mehr Daten nach außen oder eine neue Zieladresse: frischer zweiter Faktor
            step_up.require(request)
        before = snapshot(access)
        secret = self.apply(request, access, data)
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
        self.forget()
        changes = diff(before, snapshot(access))
        if changes:
            record(self.org, request.user, "update", access, changes)
        if data["_personal_new"]:
            notify.personal(access, request.user)
        if data["_writes_new"]:
            notify.writes(access, request.user)
        out = _dump(access, _reads(self.org).get(access.pk))
        if secret:
            out["webhook_secret"] = secret
        return Response(ApiAccessChangedSerializer(out).data)

    @extend_schema(responses={204: None})
    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        access = self.access(pk)
        record(self.org, request.user, "delete", access, diff(snapshot(access), {}))
        access.delete()
        self.forget()
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


class ApiAccessWebhookSecretView(_Base):
    """POST: neues Geheimnis ``hpw_…`` für die Unterschrift der Benachrichtigungen (einmal
    gezeigt; das bisherige gilt sofort nicht mehr)."""

    @extend_schema(request=None, responses=WebhookSecretSerializer)
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        step_up.require(request)
        access = self.access(pk)
        secret = access.webhook_secret = new_hook_secret()
        access.save(update_fields=["webhook_secret"])
        record(
            self.org,
            request.user,
            "update",
            access,
            {"Geheimnis der Benachrichtigungen": [None, "neu erzeugt"]},
        )
        return Response(WebhookSecretSerializer({**_dump(access), "webhook_secret": secret}).data)


class ApiAccessWebhookTestView(_Base):
    """POST: Probenachricht „ping“ sofort an die Adresse senden."""

    @extend_schema(request=None, responses=WebhookTestSerializer)
    def post(self, request, org_id: int, pk: int):
        access = self.access(pk)
        error = webhooks.test(access)
        return Response(WebhookTestSerializer({"ok": not error, "error": error}).data)
