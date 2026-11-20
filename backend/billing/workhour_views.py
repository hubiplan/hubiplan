"""Arbeitsstunden mit Ersatzbeitrag: Einstellung je Mitgliedsart und Stand je Mitglied."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from access.modules import module_on
from audit.log import record
from members.models import MemberType
from organizations.models import Organization

from . import services, workhours
from .models import WorkHourRule
from .views import BillingMixin


def _num(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


class WorkHoursView(BillingMixin, APIView):
    """GET Einstellung; PUT {min_age, max_age, rows: [{member_type, hours, rate}]}.

    Leere Stunden heißen: keine Pflichtstunden für diese Mitgliedsart."""

    allowed_org_types = (Organization.Type.CLUB,)

    def data(self) -> dict:
        cfg = services.settings_for(self.org)
        rules = {r.member_type_id: r for r in WorkHourRule.objects.filter(organization=self.org)}
        year = self.org.fiscal_year_of(timezone.localdate())
        return {
            "helpers_on": module_on(self.org, "helpers"),
            "min_age": cfg.work_min_age,
            "max_age": cfg.work_max_age,
            "years": [
                {"year": y, "label": self.org.fiscal_label(y)} for y in (year, year - 1, year - 2)
            ],
            "rows": [
                {
                    "member_type": t.pk,
                    "name": t.name,
                    "active": t.active,
                    "hours": _num(rules[t.pk].hours) if t.pk in rules else None,
                    "rate": _num(rules[t.pk].rate) if t.pk in rules else None,
                }
                for t in MemberType.objects.filter(
                    organization=self.org, is_archived=False
                ).order_by("sort_order", "name")
            ],
        }

    def get(self, request, org_id: int):
        return Response(self.data())

    @staticmethod
    def _value(raw, digits: int, key: str) -> Decimal | None:
        if raw in (None, ""):
            return None
        field = serializers.DecimalField(max_digits=digits, decimal_places=2, min_value=0)
        try:
            return field.to_internal_value(raw)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({key: exc.detail}) from exc

    @staticmethod
    def _age(raw, key: str) -> int | None:
        if raw in (None, ""):
            return None
        field = serializers.IntegerField(min_value=0, max_value=120)
        try:
            return field.to_internal_value(raw)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({key: exc.detail}) from exc

    @transaction.atomic
    def put(self, request, org_id: int):
        data = request.data if isinstance(request.data, dict) else {}
        cfg = services.settings_for(self.org)
        changes: dict = {}
        if "min_age" in data or "max_age" in data:
            min_age = self._age(data.get("min_age"), "min_age")
            max_age = self._age(data.get("max_age"), "max_age")
            if min_age is not None and max_age is not None and min_age > max_age:
                raise serializers.ValidationError(
                    {
                        "max_age": gettext(
                            "Das Höchstalter muss mindestens so hoch sein wie das Mindestalter."
                        )
                    }
                )
            if (cfg.work_min_age, cfg.work_max_age) != (min_age, max_age):
                changes[gettext("Arbeitsstunden ab Alter")] = [cfg.work_min_age, min_age]
                changes[gettext("Arbeitsstunden bis Alter")] = [cfg.work_max_age, max_age]
                cfg.work_min_age, cfg.work_max_age = min_age, max_age
                cfg.save(update_fields=["work_min_age", "work_max_age"])
        if changes:
            record(self.org, request.user, "update", cfg, changes)
        types = {t.pk: t for t in MemberType.objects.filter(organization=self.org)}
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            mt = types.get(row.get("member_type"))
            if mt is None:
                raise serializers.ValidationError(gettext("Unbekannte Mitgliedsart."))
            key = str(mt.pk)
            hours = self._value(row.get("hours"), 5, f"hours-{key}")
            rate = self._value(row.get("rate"), 8, f"rate-{key}")
            existing = WorkHourRule.objects.filter(member_type=mt).first()
            label = gettext("Arbeitsstunden {name}").format(name=mt.name)
            if not hours:
                if existing:
                    record(
                        self.org,
                        request.user,
                        "delete",
                        existing,
                        {label: [f"{existing.hours:.2f} × {existing.rate:.2f}", None]},
                    )
                    existing.delete()
                continue
            rate = rate if rate is not None else Decimal("0")
            new = f"{hours:.2f} × {rate:.2f}"
            if existing is None:
                rule = WorkHourRule.objects.create(
                    organization=self.org, member_type=mt, hours=hours, rate=rate
                )
                record(self.org, request.user, "create", rule, {label: [None, new]})
            elif (existing.hours, existing.rate) != (hours, rate):
                old = f"{existing.hours:.2f} × {existing.rate:.2f}"
                existing.hours, existing.rate = hours, rate
                existing.save(update_fields=["hours", "rate"])
                record(self.org, request.user, "update", existing, {label: [old, new]})
        return Response(self.data())


class WorkHoursBalanceView(BillingMixin, APIView):
    """Stand je Mitglied für ein Geschäftsjahr: Soll, geleistet, fehlend, Ersatzbeitrag."""

    allowed_org_types = (Organization.Type.CLUB,)

    def get(self, request, org_id: int):
        raw = str(request.query_params.get("jahr") or "")
        year = int(raw) if raw.isdigit() else self.org.fiscal_year_of(timezone.localdate())
        rows = sorted(
            workhours.balances(self.org, year).values(),
            key=lambda b: (-b.missing, b.name.casefold()),
        )
        return Response(
            {
                "year": year,
                "label": self.org.fiscal_label(year),
                "people": [
                    {
                        "membership": b.membership_id,
                        "name": b.name,
                        "member_type": b.member_type,
                        "required": _num(b.required),
                        "done": _num(b.done),
                        "missing": _num(b.missing),
                        "amount": _num(b.amount),
                    }
                    for b in rows
                ],
                "total": _num(sum((b.amount for b in rows), Decimal("0"))),
            }
        )
