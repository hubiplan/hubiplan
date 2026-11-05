"""Statistiken für Wettbewerbsberechtigte, die Mitgliedsakte und den eigenen Zugang."""

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    COMPETITIONS_MANAGE,
    COMPETITIONS_RESULTS,
    COMPETITIONS_VIEW,
    MEMBERS_VIEW,
    RESULTS_VIEW,
)
from core.api_base import OrgScopedMixin
from members.models import Membership
from organizations.models import Organization

from .models import Competition, Starter
from .statistics import competition_statistics
from .views import MODULE, _Mixin


class StatisticsQuery(serializers.Serializer):
    year = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    form = serializers.ChoiceField(
        choices=Competition.Form.choices, required=False, allow_blank=True
    )
    group = serializers.RegexField(r"^[0-9a-f]{24}$", required=False, allow_blank=True)
    membership = serializers.IntegerField(min_value=1, required=False)


def _query(request):
    query = StatisticsQuery(data=request.query_params)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    return {
        "year": data.get("year"),
        "form": data.get("form", ""),
        "group_id": data.get("group", ""),
    }


class StatisticsView(_Mixin, APIView):
    def get(self, request, org_id):
        person_id = None
        query = StatisticsQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        if membership := query.validated_data.get("membership"):
            person_id = get_object_or_404(
                Membership, organization=self.org, pk=membership, purged_at__isnull=True
            ).person_id
        data = competition_statistics(self.org, person_id=person_id, **_query(request))
        options = {}
        for st in (
            Starter.objects.filter(
                organization=self.org,
                competition__status=Competition.Status.FINAL,
                membership__organization=self.org,
                membership__purged_at__isnull=True,
                out_of_competition=False,
            )
            .select_related("membership")
            .order_by("competition__date", "pk")
        ):
            options[st.membership.person_id] = {"membership": st.membership_id, "name": st.name}
        data["member_options"] = sorted(options.values(), key=lambda m: m["name"].casefold())
        data["can_open"] = True
        return Response(data)


class MemberStatisticsView(OrgScopedMixin, APIView):
    allowed_org_types = (Organization.Type.CLUB, Organization.Type.FEDERATION)
    read_permission = MEMBERS_VIEW

    def get(self, request, org_id, membership_id):
        if MODULE not in (self.org.enabled_modules or []):
            raise NotFound(gettext("Das Modul Wettbewerbe ist nicht freigeschaltet."))
        membership = get_object_or_404(
            Membership, organization=self.org, pk=membership_id, purged_at__isnull=True
        )
        data = competition_statistics(self.org, person_id=membership.person_id, **_query(request))
        data["can_open"] = bool(
            {COMPETITIONS_MANAGE, COMPETITIONS_RESULTS, COMPETITIONS_VIEW, RESULTS_VIEW}
            & self.org_permissions
        )
        return Response(data)


class PortalStatisticsView(APIView):
    def get(self, request, access_id):
        from core.tenancy import tenant_context
        from portal.views import _portal_access

        access = _portal_access(request.user, access_id)
        org = access.organization
        if MODULE not in (org.enabled_modules or []):
            raise NotFound(gettext("Das Modul Wettbewerbe ist nicht freigeschaltet."))
        with tenant_context(org.pk, request.user.pk):
            data = competition_statistics(
                org, person_id=access.membership.person_id, **_query(request)
            )
        # Der Portalzugang bietet weder Mitgliedsnummern noch Links in die Verwaltung an.
        data["members"] = []
        for result in data["results"]:
            result.pop("membership", None)
        return Response(data)
