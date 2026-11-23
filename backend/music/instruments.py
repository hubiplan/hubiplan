"""Einstellungen › Musik › Instrumente: Liste pflegen (konzepte/instrumente.md).

Umbenennen zieht alle Verwendungen mit, Löschen geht nur bei unbenutzten Einträgen.
"""

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.log import record

from .instrument_list import USERS, ensure_defaults, key, lookup, usage
from .models import INSTRUMENT_GROUPS, Instrument
from .views import MusicViewSet, ScopedSerializer


class InstrumentSerializer(ScopedSerializer):
    group = serializers.ChoiceField(choices=INSTRUMENT_GROUPS, required=False)
    name = serializers.CharField(max_length=100)
    used = serializers.SerializerMethodField()

    def get_used(self, obj) -> int:
        counts = self.context.get("usage")
        if counts is None:
            counts = usage(obj.organization)
        return counts.get(key(obj.name), 0)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte einen Namen angeben."))
        org = self.context["view"].org
        clash = lookup(org).get(key(value))
        if clash and clash != self.instance:
            raise serializers.ValidationError(gettext("Dieses Instrument gibt es schon."))
        return value

    class Meta:
        model = Instrument
        fields = ["id", "name", "group", "position", "active", "used"]
        read_only_fields = ["position"]


class InstrumentViewSet(MusicViewSet):
    """Einstellungen › Musik › Instrumente."""

    serializer_class = InstrumentSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]

    def get_queryset(self):
        return Instrument.objects.filter(organization=self.org).order_by("position", "pk")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "list":
            context["usage"] = usage(self.org)
        return context

    def list(self, request, *args, **kwargs):
        with transaction.atomic():
            ensure_defaults(self.org)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        ensure_defaults(self.org)
        last = Instrument.objects.filter(organization=self.org).aggregate(m=Max("position"))["m"]
        try:
            with transaction.atomic():
                serializer.validated_data["position"] = min((last or 0) + 1, 32767)
                super().perform_create(serializer)
        except IntegrityError as exc:
            raise serializers.ValidationError(gettext("Dieses Instrument gibt es schon.")) from exc

    @transaction.atomic
    def perform_update(self, serializer):
        old = Instrument.objects.select_for_update().get(pk=serializer.instance.pk).name
        try:
            with transaction.atomic():
                super().perform_update(serializer)
        except IntegrityError as exc:
            raise serializers.ValidationError(gettext("Dieses Instrument gibt es schon.")) from exc
        new = serializer.instance.name
        if new != old:
            # Umbenennen zieht alle Verwendungen mit (gleicher Schlüssel wie der alte Name)
            old_key = key(old)
            for model in USERS:
                ids = [
                    pk
                    for pk, name in model.objects.filter(organization=self.org).values_list(
                        "pk", "instrument"
                    )
                    if name and key(name) == old_key
                ]
                if ids:
                    model.objects.filter(pk__in=ids).update(instrument=new)

    def perform_destroy(self, instance):
        if usage(self.org).get(key(instance.name)):
            raise serializers.ValidationError(
                gettext("Dieses Instrument wird noch verwendet. Bitte stattdessen ausblenden.")
            )
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def order(self, request, org_id):
        """Reihenfolge setzen: Liste aller Nummern in der gewünschten Folge."""
        ids = serializers.ListField(
            child=serializers.IntegerField(min_value=1), max_length=1000
        ).run_validation(request.data.get("ids"))
        rows = {
            i.pk: i for i in Instrument.objects.select_for_update().filter(organization=self.org)
        }
        if set(ids) != set(rows) or len(ids) != len(rows):
            raise serializers.ValidationError(gettext("Bitte alle Instrumente der Liste angeben."))
        before = [rows[pk].name for pk in sorted(rows, key=lambda pk: rows[pk].position)]
        for position, pk in enumerate(ids, start=1):
            if rows[pk].position != position:
                rows[pk].position = position
                rows[pk].save(update_fields=["position"])
        after = [rows[pk].name for pk in ids]
        if before != after:
            record(self.org, request.user, "update", rows[ids[0]], {"Reihenfolge": [before, after]})
        return Response({"ok": True})
