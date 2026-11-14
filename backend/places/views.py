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
from .models import Place, join_name

# Vorschläge: Orte, die in dieser Zeit mindestens so oft vorkamen
SUGGEST_YEARS = 2
SUGGEST_MIN = 2
SUGGEST_LIMIT = 20


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "id",
            "parent",
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
        return value

    def validate_parent(self, value):
        if value is None:
            return None
        if value.organization_id != self.context["org"].pk or value.parent_id:
            raise serializers.ValidationError(_("Räume gehören in einen eigenen Ort."))
        if self.instance is not None:
            if value.pk == self.instance.pk:
                raise serializers.ValidationError(_("Räume gehören in einen eigenen Ort."))
            if self.instance.rooms.exists():
                raise serializers.ValidationError(
                    _("Ein Ort mit Räumen kann nicht selbst Raum werden.")
                )
        return value

    def _check_names(self, parent, name):
        org = self.context["org"]
        own = Place.objects.filter(organization=org)
        if self.instance is not None:
            own = own.exclude(pk=self.instance.pk)
        siblings = own.filter(parent=parent) if parent else own.filter(parent__isnull=True)
        if siblings.filter(name__iexact=name).exists():
            if parent:
                raise serializers.ValidationError(
                    {"name": _("Einen Raum mit diesem Namen gibt es hier schon.")}
                )
            raise serializers.ValidationError(
                {"name": _("Einen Ort mit diesem Namen gibt es schon.")}
            )
        # „Gebäude, Raum“ darf keinem anderen Ort gleichen (sonst ist die Auswahl mehrdeutig)
        full = join_name(parent.name, name) if parent else name
        names = {p.full_name.lower() for p in own.select_related("parent")}
        if full.lower() in names:
            raise serializers.ValidationError(
                {"name": _("Einen Ort mit diesem Namen gibt es schon.")}
            )
        if len(full) > 200:
            raise serializers.ValidationError(
                {"name": _("Gebäude und Raum zusammen dürfen höchstens 200 Zeichen lang sein.")}
            )
        if self.instance is not None and not parent and name != self.instance.name:
            for room in self.instance.rooms.all():
                if len(join_name(name, room.name)) > 200:
                    raise serializers.ValidationError(
                        {
                            "name": _(
                                "Gebäude und Raum zusammen dürfen höchstens 200 Zeichen lang sein."
                            )
                        }
                    )

    def validate(self, attrs):
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        name = attrs.get("name", getattr(self.instance, "name", ""))
        if "name" in attrs or "parent" in attrs or self.instance is None:
            self._check_names(parent, name)
        if parent is not None:
            # Anschrift und Kartenpunkt kommen vom Gebäude
            attrs["address"] = ""
            attrs["latitude"] = None
            attrs["longitude"] = None
        lat = attrs.get("latitude", getattr(self.instance, "latitude", None))
        lon = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (lat is None) != (lon is None):
            raise serializers.ValidationError(
                {"latitude": _("Bitte Breite und Länge zusammen angeben.")}
            )
        return attrs


def _number(value):
    return None if value is None else float(value)


def place_data(place: Place, scope: access.Scope) -> dict:
    data = PlaceSerializer(place).data
    for key in ("latitude", "longitude"):
        data[key] = _number(data[key])
    data["full_name"] = place.full_name
    # Was ein Formular beim Auswählen übernimmt (Räume: Anschrift usw. vom Gebäude)
    pick = place.effective()
    pick["latitude"] = _number(pick["latitude"])
    pick["longitude"] = _number(pick["longitude"])
    data["pick"] = pick
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
        return Place.objects.filter(organization_id__in=ids).select_related(
            "organization", "parent"
        )

    def own(self, pk: int) -> Place:
        return get_object_or_404(Place, organization=self.scope.org, pk=pk)


class ListView(Base):
    def get(self, request, **kwargs):
        qs = self.visible()
        if request.query_params.get("alle") != "1":
            qs = qs.filter(is_active=True).exclude(parent__is_active=False)
        rows = sorted(
            qs, key=lambda p: (p.organization_id != self.scope.org.pk, p.full_name.lower())
        )
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
    saved = {
        p.full_name.lower() for p in Place.objects.filter(organization=org).select_related("parent")
    }
    rows = [e for k, e in by_name.items() if k not in saved and e["count"] >= SUGGEST_MIN]
    rows.sort(key=lambda e: (-e["count"], e["name"].lower()))
    return rows[:SUGGEST_LIMIT]


class SuggestionsView(Base):
    def get(self, request, **kwargs):
        access.require_manage(self.scope)
        return Response(suggestions(self.scope.org))
