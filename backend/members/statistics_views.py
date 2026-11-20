"""API der Mitgliederentwicklung für Verein, Dachverband und Abteilung."""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from portal.views import DepartmentScopedMixin

from . import census, statistics
from .federation_views import _FederationMixin
from .views import _ClubMixin


class ClubStatisticsView(_ClubMixin, APIView):
    def get(self, request, org_id: int):
        return Response(
            statistics.statistics(statistics.club_source(self.org), request.query_params)
        )


class FederationStatisticsView(_FederationMixin, APIView):
    def get(self, request, org_id: int):
        src = statistics.federation_source(self.org)
        return Response(statistics.statistics(src, request.query_params))


class DepartmentStatisticsView(DepartmentScopedMixin, APIView):
    def get(self, request, dept_id: int):
        src = statistics.department_source(self.dept)
        return Response(statistics.statistics(src, request.query_params))


FILE_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}


def census_response(request, org, src):
    """Stichtagsstatistik als JSON oder Datei (``?als=pdf|xlsx|csv``)."""
    data = census.census(src, request.query_params)
    fmt = request.query_params.get("als")
    if fmt not in FILE_TYPES:
        return Response(data)
    render = {"pdf": census.render_pdf, "xlsx": census.render_xlsx, "csv": census.render_csv}
    response = HttpResponse(render[fmt](org, data), content_type=FILE_TYPES[fmt])
    download = fmt != "pdf" or request.query_params.get("download") == "1"
    name = f"Mitglieder-Stichtag-{data['stichtag']:%Y-%m-%d}"
    response["Content-Disposition"] = (
        f'{"attachment" if download else "inline"}; filename="{name}.{fmt}"'
    )
    response["Cache-Control"] = "private, no-store"
    return response


class ClubCensusView(_ClubMixin, APIView):
    def get(self, request, org_id: int):
        return census_response(request, self.org, statistics.club_source(self.org))


class FederationCensusView(_FederationMixin, APIView):
    def get(self, request, org_id: int):
        return census_response(request, self.org, statistics.federation_source(self.org))


class DepartmentCensusView(DepartmentScopedMixin, APIView):
    def get(self, request, dept_id: int):
        src = statistics.department_source(self.dept)
        return census_response(request, self.dept.organization, src)
