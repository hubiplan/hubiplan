"""API Anlagenverzeichnis: /api/orgs/<org_id>/finance/assets/ (Modul Steuern & Gemeinnützigkeit).

Lesen mit finance.view, Ändern mit finance.edit. ``GET ?jahr=`` liefert die Anlagen mit AfA
und Buchwerten des Geschäftsjahres, ``&als=xlsx`` als Tabelle."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from access.modules import module_on
from core.api_base import AuditMixin, ModelCleanMixin

from . import assets
from .models import Booking, FixedAsset
from .serializers import OrgRelatedField
from .views import FinanceMixin, _file_response


class MaterialChoiceField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        from materials.models import MaterialItem

        return MaterialItem.objects.filter(
            organization=self.context["org"], deleted_at__isnull=True
        )


class FixedAssetSerializer(ModelCleanMixin, serializers.ModelSerializer):
    booking = OrgRelatedField(queryset=Booking.objects.none(), allow_null=True, required=False)
    booking_number = serializers.SerializerMethodField()
    material_item = MaterialChoiceField(allow_null=True, required=False)
    material_name = serializers.SerializerMethodField()
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    tax_area_label = serializers.CharField(source="get_tax_area_display", read_only=True)
    disposal_label = serializers.CharField(source="get_disposal_display", read_only=True)
    values = serializers.SerializerMethodField()

    class Meta:
        model = FixedAsset
        fields = [
            "id",
            "name",
            "acquired_on",
            "cost",
            "net_cost",
            "tax_area",
            "tax_area_label",
            "method",
            "method_label",
            "useful_life",
            "booking",
            "booking_number",
            "material_item",
            "material_name",
            "disposal",
            "disposal_label",
            "disposed_on",
            "note",
            "values",
        ]

    def get_booking_number(self, obj) -> str | None:
        return obj.booking.display_number if obj.booking_id else None

    def get_material_name(self, obj) -> str | None:
        return obj.material_item.title if obj.material_item_id else None

    def get_values(self, obj) -> dict | None:
        year = self.context.get("year")
        if year is None:
            return None
        v = assets.year_values(obj, self.context["org"], year)
        return {k: f"{value:.2f}" for k, value in v.items()}


class FixedAssetViewSet(FinanceMixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = FixedAssetSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not module_on(self.org, "tax"):
            raise NotFound(gettext("Nicht gefunden."))

    def get_queryset(self):
        return FixedAsset.objects.filter(organization=self.org).select_related(
            "booking__organization", "material_item"
        )

    def get_create_kwargs(self) -> dict:
        return {"organization": self.org}

    def _year(self) -> int:
        raw = self.request.query_params.get("jahr", "")
        if raw.isdigit() and 1990 <= int(raw) <= 2100:
            return int(raw)
        return self.org.fiscal_year_of(timezone.localdate())

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["year"] = self._year()
        return ctx

    def list(self, request, *args, **kwargs):
        year = self._year()
        data = assets.register(self.org, year)
        if request.query_params.get("als") == "xlsx":
            return _file_response(
                render_xlsx(self.org, data),
                f"Anlagenverzeichnis-{data['label']}",
                "xlsx",
                True,
            )
        rows = FixedAssetSerializer(
            [r["asset"] for r in data["rows"]], many=True, context=self.get_serializer_context()
        ).data
        return Response(
            {
                "year": year,
                "label": data["label"],
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "assets": rows,
                "totals": {k: f"{v:.2f}" for k, v in data["totals"].items()},
                "suggest_from": f"{assets.SUGGEST_FROM:.2f}",
            }
        )

    @action(detail=False, methods=["get"])
    def materials(self, request, org_id: int):
        """Gegenstände im Inventar zur Auswahl (nur mit Modul Material)."""
        if not module_on(self.org, "material"):
            return Response([])
        from materials.models import MaterialItem

        items = MaterialItem.objects.filter(organization=self.org, deleted_at__isnull=True)
        rows = sorted(
            ({"id": item.pk, "name": item.title} for item in items),
            key=lambda r: r["name"].casefold(),
        )
        return Response(rows)


def render_xlsx(org, data: dict) -> bytes:
    from .project_report import _xlsx

    head = [
        "Bezeichnung",
        "Anschaffung",
        "Anschaffungskosten",
        "Bereich",
        "Abschreibung",
        "Nutzungsdauer",
        "Buchwert Anfang",
        "AfA",
        "Restwert Abgang",
        "Buchwert Ende",
        "Abgang",
        "Beleg",
    ]
    rows = []
    for r in data["rows"]:
        a = r["asset"]
        rows.append(
            [
                a.name,
                a.acquired_on.strftime("%d.%m.%Y"),
                a.cost,
                str(a.get_tax_area_display()),
                str(a.get_method_display()),
                a.useful_life if a.method == FixedAsset.Method.LINEAR else "",
                r["book_start"],
                r["depreciation"],
                r["residual"],
                r["book_end"],
                f"{a.get_disposal_display()} {a.disposed_on:%d.%m.%Y}" if a.disposal else "",
                a.booking.display_number if a.booking_id else "",
            ]
        )
    return _xlsx(org, [(f"Anlagen {data['label']}", [head, *rows])], money_from=2)
