"""Haushaltsplan: Ansicht, Speichern, Beschluss, Vorlage aus dem Vorjahr, PDF und Excel."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record

from . import budget, budget_report, services
from .views import FinanceMixin, _file_response


def _year(org, request) -> int:
    raw = request.query_params.get("jahr", "")
    if raw.isdigit() and 1990 <= int(raw) <= 2100:
        return int(raw)
    return org.fiscal_year_of(timezone.localdate())


def _version(request):
    value = request.data.get("version")
    return value if isinstance(value, int) else None


class BudgetView(FinanceMixin, APIView):
    """GET Plan und Ist (?jahr=JJJJ, ?als=pdf|xlsx), PUT Zeilen eines Entwurfs ersetzen,
    DELETE Entwurf löschen."""

    @extend_schema(responses=dict)
    def get(self, request, org_id: int):
        year = _year(self.org, request)
        data = budget.report(self.org, year)
        fmt = request.query_params.get("als")
        if fmt in ("pdf", "xlsx"):
            content = (
                budget_report.render_pdf(self.org, data)
                if fmt == "pdf"
                else budget_report.render_xlsx(self.org, data)
            )
            return _file_response(
                content,
                f"Haushaltsplan-{data['label']}",
                fmt,
                request.query_params.get("download") == "1",
            )
        return Response(services._money(data))

    @extend_schema(request=dict, responses=dict)
    def put(self, request, org_id: int):
        year = _year(self.org, request)
        if not isinstance(request.data, dict):
            raise serializers.ValidationError({"lines": gettext("Ungültige Anfrage.")})
        try:
            plan, changes = budget.save(self.org, year, request.data, request.user)
        except budget.BudgetError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        if changes:
            record(self.org, request.user, "update", plan, changes)
        return Response(services._money(budget.report(self.org, year)))

    @extend_schema(responses=dict)
    def delete(self, request, org_id: int):
        year = _year(self.org, request)
        try:
            removed = budget.delete(self.org, year, _version(request))
        except budget.BudgetError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        if removed is not None:
            record(self.org, request.user, "delete", removed, {})
        return Response(services._money(budget.report(self.org, year)))


class BudgetStatusView(FinanceMixin, APIView):
    """POST {status: draft|adopted, adopted_on, adopted_by, version}."""

    @extend_schema(request=dict, responses=dict)
    def post(self, request, org_id: int):
        year = _year(self.org, request)
        try:
            plan, changes = budget.set_status(self.org, year, request.data, request.user)
        except budget.BudgetError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        record(self.org, request.user, "update", plan, changes)
        return Response(services._money(budget.report(self.org, year)))


class BudgetCopyView(FinanceMixin, APIView):
    """POST {source: plan|actual, version}: Plan oder Ist des Vorjahres als Entwurf übernehmen."""

    @extend_schema(request=dict, responses=dict)
    def post(self, request, org_id: int):
        year = _year(self.org, request)
        try:
            plan, changes = budget.copy_previous(
                self.org, year, request.data.get("source"), request.user, _version(request)
            )
        except budget.BudgetError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        if changes:
            record(self.org, request.user, "update", plan, changes)
        return Response(services._money(budget.report(self.org, year)))
