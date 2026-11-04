from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from changes.tracking import active, suppress
from core.tenancy import rls_bypass

from .access import can_delete, can_edit
from .attachments import Conflict
from .models import TodoSeries
from .series import lock_task, snapshot_template
from .sharing import log_change
from .views import TodoScopeMixin


class SeriesInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    repeat = serializers.ChoiceField(
        choices=["daily", "weekly", "monthly", "yearly"], required=False
    )
    interval = serializers.IntegerField(min_value=1, max_value=365, required=False)
    basis = serializers.ChoiceField(choices=["due", "done"], required=False)
    last_day = serializers.BooleanField(required=False)
    ends_on = serializers.DateField(allow_null=True, required=False)
    count = serializers.IntegerField(min_value=1, max_value=10000, allow_null=True, required=False)
    active = serializers.BooleanField(required=False)
    deleted = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if attrs.get("ends_on") and attrs.get("count"):
            raise serializers.ValidationError(
                gettext("Bitte entweder Enddatum oder Anzahl wählen.")
            )
        return attrs


def series_data(todo):
    if not todo.series_id:
        return None
    series = todo.series
    return {
        "id": series.pk,
        "sequence_no": todo.sequence_no,
        "active": series.active,
        "version": series.version,
        "repeat": series.repeat,
        "interval": series.interval,
        "basis": series.basis,
        "last_day": series.last_day,
        "ends_on": series.ends_on,
        "count": series.count,
        "deleted_at": series.deleted_at,
    }


class SeriesView(TodoScopeMixin, APIView):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        restoring = request.data.get("deleted") is False
        todo = lock_task(request.user, self.scope, pk, deleted=restoring)
        if not can_edit(todo, request.user, self.scope):
            raise PermissionDenied()
        serializer = SeriesInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values.pop("version") != todo.version:
            raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
        ctx = active()
        if ctx:
            ctx.block(gettext("Serienregeln und Serien-Papierkorb werden an der Serie verwaltet."))
        if "deleted" in values:
            if not todo.series_id or not can_delete(todo, request.user, self.scope):
                raise PermissionDenied()
            series = todo.series
            deleted = values.pop("deleted")
            if values:
                raise serializers.ValidationError(
                    gettext("Bitte die Serie getrennt löschen oder wiederherstellen.")
                )
            stamp = series.deleted_at
            if not deleted and stamp is None:
                raise serializers.ValidationError(gettext("Die Serie liegt nicht im Papierkorb."))
            series.deleted_at = timezone.now() if deleted else None
            series.version += 1
            series.save()
            with suppress():
                rows = series.occurrences.filter(withdrawn=False)
                rows = (
                    rows.filter(deleted_at__isnull=True)
                    if deleted
                    else rows.filter(deleted_at=stamp)
                )
                for item in rows.order_by("pk"):
                    item.deleted_at = series.deleted_at
                    item.version += 1
                    item.save(update_fields=["deleted_at", "version", "updated_at"])
            log_change(todo, request.user, "delete" if deleted else "update")
            return Response({"series": series_data(todo)})
        if todo.series_id and set(values) == {"active"}:
            series = todo.series
            series.active = values["active"]
            series.version += 1
            series.save(update_fields=["active", "version"])
            todo.version += 1
            todo.save(update_fields=["version", "updated_at"])
            log_change(todo, request.user, "update")
            return Response({"series": series_data(todo), "version": todo.version})
        if todo.status != "open" or not todo.due_date:
            raise serializers.ValidationError(
                gettext("Wiederholungen brauchen eine offene Aufgabe mit Frist.")
            )
        if todo.series_id:
            series = todo.series
        else:
            if "repeat" not in values:
                raise serializers.ValidationError(gettext("Bitte eine Wiederholregel wählen."))
            series = TodoSeries(
                organization=todo.organization,
                department_id=todo.department_id,
                owner=todo.owner,
                anchor_date=todo.due_date,
            )
        for key, value in values.items():
            if key == "repeat" and series.pk and value != series.repeat:
                series.anchor_date = todo.due_date
            setattr(series, key, value)
        if series.ends_on and series.count:
            raise serializers.ValidationError(
                gettext("Bitte entweder Enddatum oder Anzahl wählen.")
            )
        if series.ends_on and series.ends_on < todo.due_date:
            raise serializers.ValidationError(
                gettext("Das Serienende liegt vor der aktuellen Frist.")
            )
        snapshot_template(todo, series)
        series.version += 1
        with rls_bypass():
            # Nur die am gesperrten Vorgang geprüfte neue bzw. geänderte Vorlage.
            series.save()
        todo.series = series
        todo.sequence_no = todo.sequence_no or 1
        todo.version += 1
        todo.save(update_fields=["series", "sequence_no", "version", "updated_at"])
        log_change(todo, request.user, "update")
        return Response({"series": series_data(todo), "version": todo.version})
