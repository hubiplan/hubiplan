"""Orte: Liste, speichern, ändern, archivieren, löschen und Vorschläge."""

import datetime
from collections import Counter

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot

from . import access
from .models import Place

# Vorschläge: Orte, die in dieser Zeit mindestens so oft vorkamen
SUGGEST_YEARS = 2
SUGGEST_MIN = 2
SUGGEST_LIMIT = 20


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "id",
            "name",
            "address",
            "directions",
            "latitude",
            "longitude",
            "is_active",
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Bitte einen Namen angeben."))
        org = self.context["org"]
        clash = Place.objects.filter(organization=org, name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(_("Einen Ort mit diesem Namen gibt es schon."))
        return value

    def validate(self, attrs):
        lat = attrs.get("latitude", getattr(self.instance, "latitude", None))
        lon = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (lat is None) != (lon is None):
            raise serializers.ValidationError(
                {"latitude": _("Bitte Breite und Länge zusammen angeben.")}
            )
        return attrs


def place_data(place: Place, scope: access.Scope) -> dict:
    data = PlaceSerializer(place).data
    for key in ("latitude", "longitude"):
        data[key] = None if data[key] is None else float(data[key])
    own = place.organization_id == scope.org.pk
    data["own"] = own
    data["owner"] = None if own else place.organization.name
    data["can_edit"] = own and scope.can_manage
    return data


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def visible(self):
        """Eigene Orte und die des Dachverbands (die RLS-Regel lässt nur diese zu)."""
        org = self.scope.org
        ids = [org.pk]
        if org.parent_id and org.parent and org.parent.type == "federation":
            ids.append(org.parent_id)
        return Place.objects.filter(organization_id__in=ids).select_related("organization")

    def own(self, pk: int) -> Place:
        return get_object_or_404(Place, organization=self.scope.org, pk=pk)


class ListView(Base):
    def get(self, request, **kwargs):
        qs = self.visible()
        if request.query_params.get("alle") != "1":
            qs = qs.filter(is_active=True)
        rows = sorted(qs, key=lambda p: (p.organization_id != self.scope.org.pk, p.name.lower()))
        return Response(
            {
                "places": [place_data(p, self.scope) for p in rows],
                "can_edit": self.scope.can_edit,
                "can_manage": self.scope.can_manage,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        data = PlaceSerializer(data=request.data, context={"org": self.scope.org})
        data.is_valid(raise_exception=True)
        place = data.save(organization=self.scope.org, created_by=request.user)
        record(self.scope.org, request.user, "create", place, diff({}, snapshot(place)))
        return Response(place_data(place, self.scope), status=status.HTTP_201_CREATED)


class DetailView(Base):
    @transaction.atomic
    def patch(self, request, pk: int, **kwargs):
        access.require_manage(self.scope)
        place = self.own(pk)
        before = snapshot(place)
        data = PlaceSerializer(
            place, data=request.data, partial=True, context={"org": self.scope.org}
        )
        data.is_valid(raise_exception=True)
        place = data.save()
        changes = diff(before, snapshot(place))
        if changes:
            record(self.scope.org, request.user, "update", place, changes)
        return Response(place_data(place, self.scope))

    @transaction.atomic
    def delete(self, request, pk: int, **kwargs):
        access.require_manage(self.scope)
        place = self.own(pk)
        record(self.scope.org, request.user, "delete", place, diff(snapshot(place), {}))
        place.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def used_places(org, since: datetime.datetime) -> Counter:
    """Wie oft Ort und Anschrift zuletzt eingetippt wurden (Termine, Wettbewerbe, Dienste)."""
    from competitions.models import Competition
    from events.models import Event
    from helpers.models import Duty

    seen: Counter = Counter()
    events = (
        Event.objects.filter(organization=org, starts_at__gte=since)
        .exclude(location="")
        .filter(remote_uid="")
        .values_list("location", "address")
    )
    for location, address in events:
        seen[(location.strip(), (address or "").strip())] += 1
    comps = (
        Competition.objects.filter(organization=org, date__gte=since.date())
        .exclude(location="")
        .values_list("location", flat=True)
    )
    for location in comps:
        seen[(location.strip(), "")] += 1
    duties = (
        Duty.objects.filter(organization=org, plan__created_at__gte=since)
        .exclude(location="")
        .values_list("location", flat=True)
    )
    for location in duties:
        seen[(location.strip(), "")] += 1
    return seen


def suggestions(org) -> list[dict]:
    since = timezone.now() - datetime.timedelta(days=365 * SUGGEST_YEARS)
    seen = used_places(org, since)
    # Gleicher Name mit und ohne Anschrift: einmal, mit der häufigsten Anschrift
    by_name: dict[str, dict] = {}
    for (name, address), count in seen.most_common():
        key = name.lower()
        entry = by_name.setdefault(key, {"name": name[:200], "address": "", "count": 0})
        entry["count"] += count
        if address and not entry["address"]:
            entry["address"] = address[:300]
    names = Place.objects.filter(organization=org).values_list("name", flat=True)
    saved = {n.lower() for n in names}
    rows = [e for k, e in by_name.items() if k not in saved and e["count"] >= SUGGEST_MIN]
    rows.sort(key=lambda e: (-e["count"], e["name"].lower()))
    return rows[:SUGGEST_LIMIT]


class SuggestionsView(Base):
    def get(self, request, **kwargs):
        access.require_manage(self.scope)
        return Response(suggestions(self.scope.org))
