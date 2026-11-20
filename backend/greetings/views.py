"""Seite „Glückwünsche“ (Rundschreiben › Glückwünsche): Einstellung, Entwürfe, Vorschau."""

from __future__ import annotations

import datetime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import CIRCULARS_SEND, CIRCULARS_VIEW
from audit.log import record
from circulars import recipients as rcp
from circulars import text
from core.api_base import OrgScopedMixin
from members.models import today
from organizations.models import Organization

from . import services
from .models import MAX_LEAD_DAYS, GreetingBatch, GreetingSettings

# So weit reicht die Vorschau auf kommende Anlässe
PREVIEW_DAYS = 60
TEXT_FIELDS = ("birthday_subject", "birthday_body", "jubilee_subject", "jubilee_body")


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GreetingSettings
        fields = [
            "birthdays",
            "round_ages",
            "every_year_from",
            "jubilees",
            "approval",
            "lead_days",
            "send_hour",
            "via_app",
            "also_mail",
            "reply_to",
            *TEXT_FIELDS,
        ]

    def validate_round_ages(self, value):
        ages = services.parse_ages(value)
        if (value or "").strip() and not ages:
            raise serializers.ValidationError(
                gettext("Bitte Lebensjahre durch Komma getrennt angeben, z. B. 50, 60, 70.")
            )
        return ", ".join(str(a) for a in ages)

    def validate_every_year_from(self, value):
        if value and not 1 <= value <= 120:
            raise serializers.ValidationError(gettext("Bitte ein Alter bis 120 angeben."))
        return value

    def validate_lead_days(self, value):
        if value > MAX_LEAD_DAYS:
            raise serializers.ValidationError(
                gettext("Höchstens {n} Tage vorher.").format(n=MAX_LEAD_DAYS)
            )
        return value

    def validate_send_hour(self, value):
        if not 6 <= value <= 20:
            raise serializers.ValidationError(gettext("Bitte eine Uhrzeit zwischen 6 und 20 Uhr."))
        return value

    def validate(self, attrs):
        unknown = text.unknown_placeholders(*(attrs.get(f, "") for f in TEXT_FIELDS))
        if unknown:
            names = ", ".join("{" + u + "}" for u in unknown)
            raise serializers.ValidationError(
                {"birthday_body": gettext("Unbekannte Platzhalter: {names}.").format(names=names)}
            )
        for field in TEXT_FIELDS:
            if field in attrs and not attrs[field].strip():
                # Leer heißt: Vorgabetext
                attrs[field] = ""
        return attrs


def settings_data(s: GreetingSettings) -> dict:
    data = {f: getattr(s, f) for f in SettingsSerializer.Meta.fields}
    data["active"] = bool(s.pk) and s.active
    data["defaults"] = services.default_texts(s.organization)
    return data


def batch_data(b: GreetingBatch, today_: datetime.date, base: str) -> dict:
    c = b.circular
    status = "skipped" if b.skipped_at else ("draft" if c and c.is_draft else "sent")
    if status == "draft" and b.date < today_:
        status = "late"
    values = (c.filters or {}).get("greeting", {}) if c else {}
    recipients = []
    if c and c.is_draft:
        # Vorschau wie beim Rundschreiben: Weg je Person, Widerspruch, Brief
        recipients = [
            {
                "name": f"{r.first_name} {r.last_name}".strip(),
                "channel": r.channel,
                "note": r.note,
            }
            for r in rcp.select(c).candidates
        ]
    return {
        "id": b.pk,
        "date": b.date,
        "kind": b.kind,
        "kind_label": b.get_kind_display(),
        "status": status,
        "note": b.note,
        "count": len(values),
        "circular": c.pk if c else None,
        "letters_url": f"{base}circulars/{c.pk}/letters/" if c else None,
        "sent_at": c.sent_at if c else None,
        "recipients": recipients,
        "letters": sum(1 for r in recipients if r["channel"] == "letter"),
    }


class _Access(OrgScopedMixin):
    read_permission = CIRCULARS_VIEW
    write_permission = CIRCULARS_SEND
    allowed_org_types = (Organization.Type.CLUB,)

    def base(self) -> str:
        return f"/api/orgs/{self.org.pk}/"

    def batch(self, pk: int) -> GreetingBatch:
        return get_object_or_404(
            GreetingBatch.objects.select_related("circular"), organization=self.org, pk=pk
        )


class OverviewView(_Access, APIView):
    """GET: Einstellung, Entwürfe und Verlauf, kommende Anlässe."""

    def get(self, request, org_id: int):
        on = today()
        s = services.settings_for(self.org)
        if s.pk and s.active:
            services.prepare(self.org, on)
        batches = GreetingBatch.objects.filter(
            organization=self.org, date__gte=on - datetime.timedelta(days=30)
        ).select_related("circular")
        upcoming = []
        if s.active:
            rows = services.occasions(self.org, s, on, on + datetime.timedelta(days=PREVIEW_DAYS))
            out = services.opted_out(r["member_id"] for r in rows)
            upcoming = [
                {
                    "date": r["date"],
                    "kind": r["kind"],
                    "member_id": r["member_id"],
                    "name": f"{r['first_name']} {r['last_name']}".strip(),
                    "age": r["age"],
                    "years": r["years"],
                    "opted_out": r["member_id"] in out,
                }
                for r in rows
            ]
        return Response(
            {
                "settings": settings_data(s),
                "batches": [batch_data(b, on, self.base()) for b in batches],
                "upcoming": upcoming,
                "can_edit": CIRCULARS_SEND in self.org_permissions,
            }
        )


class SettingsView(_Access, APIView):
    def get(self, request, org_id: int):
        return Response(settings_data(services.settings_for(self.org)))

    @transaction.atomic
    def put(self, request, org_id: int):
        s = services.settings_for(self.org)
        before = {f: getattr(s, f) for f in SettingsSerializer.Meta.fields} if s.pk else {}
        ser = SettingsSerializer(s, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        s = ser.save(organization=self.org, updated_by=request.user)
        after = {f: getattr(s, f) for f in SettingsSerializer.Meta.fields}
        changes = {
            k: [before.get(k), v]
            for k, v in after.items()
            if before.get(k) != v and k not in TEXT_FIELDS
        }
        if any(before.get(k) != after[k] for k in TEXT_FIELDS):
            changes["Texte"] = [None, "geändert"]
        if changes:
            record(self.org, request.user, "update", s, changes)
        services.prepare(self.org, today())
        return Response(settings_data(services.settings_for(self.org)))


class SendView(_Access, APIView):
    def post(self, request, org_id: int, pk: int):
        b = self.batch(pk)
        counts = services.send(b, request.user)
        record(
            self.org,
            request.user,
            "update",
            b.circular,
            {"Glückwunsch versendet": [None, b.date.isoformat()]},
        )
        return Response({"sent": counts})


class SkipView(_Access, APIView):
    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        b = self.batch(pk)
        services.skip(b, request.user, gettext("ausgelassen"))
        record(
            self.org, request.user, "update", b, {"Glückwunsch ausgelassen": [None, str(b.date)]}
        )
        return Response({"ok": True})


class RestoreView(_Access, APIView):
    """Ausgelassenen Glückwunsch wieder vorsehen (nur ab heute)."""

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        b = self.batch(pk)
        if not b.skipped_at or b.date < today():
            raise serializers.ValidationError(
                gettext("Nur ausgelassene Glückwünsche ab heute lassen sich wieder vorsehen.")
            )
        b.delete()
        services.prepare(self.org, today())
        return Response({"ok": True})
