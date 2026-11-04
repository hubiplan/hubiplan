"""Notenbestand, Dokumentenrechte, Programm und Vorbereitung."""

import csv
import io
from collections import Counter

from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.api_base import OrgScopedMixin
from documents import services as documents
from documents.models import Document
from documents.views import file_response

from .models import Arrangement, Performance, Piece, ProgramEntry, ScoreDocument, ScorePart
from .views import MusicViewSet, PerformanceViewSet, ScopedSerializer


def visible_documents(view):
    if "docs.view" not in view.org_permissions:
        return Document.objects.none()
    folders = documents.org_viewer(view.org, view.org_permissions).all_folders()
    return Document.objects.filter(organization=view.org, folder__in=folders, deleted_at=None)


class MusicPieceSerializer(ScopedSerializer):
    class Meta:
        model = Piece
        fields = ["id", "title", "composer"]


class MusicArrangementSerializer(ScopedSerializer):
    duration_seconds = serializers.IntegerField(min_value=0, max_value=86400)

    class Meta:
        model = Arrangement
        fields = [
            "id",
            "piece",
            "name",
            "arranger",
            "publisher",
            "duration_seconds",
            "difficulty",
            "ensemble",
            "license_note",
            "active",
        ]


class MusicScorePartSerializer(ScopedSerializer):
    kind = serializers.ChoiceField(choices=["part", "score"])
    paper_format = serializers.ChoiceField(choices=["concert", "march"])
    required_players = serializers.IntegerField(min_value=0, max_value=500)
    copies = serializers.IntegerField(min_value=0, max_value=10000)

    class Meta:
        model = ScorePart
        fields = [
            "id",
            "arrangement",
            "instrument",
            "register",
            "kind",
            "paper_format",
            "required_players",
            "copies",
            "location",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            outstanding = (
                self.instance.loans.aggregate(n=Sum(F("quantity") - F("returned")))["n"] or 0
            )
            if attrs.get("copies", self.instance.copies) < outstanding or (
                outstanding
                and any(
                    k in attrs and attrs[k] != getattr(self.instance, k)
                    for k in ("arrangement", "instrument", "register", "kind", "paper_format")
                )
            ):
                raise serializers.ValidationError(
                    gettext(
                        "Bitte zuerst ausgegebene Noten zurücknehmen; der Bestand darf "
                        "ausstehende Ausgaben nicht unterschreiten."
                    )
                )
        return attrs


class MusicScoreDocumentSerializer(ScopedSerializer):
    title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = ScoreDocument
        fields = ["id", "arrangement", "part", "document", "title", "usage_note"]

    def get_fields(self):
        fields = super().get_fields()
        view = self.context.get("view")
        fields["document"].queryset = (
            visible_documents(view) if getattr(view, "org", None) else Document.objects.none()
        )
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        arrangement = attrs.get("arrangement", getattr(self.instance, "arrangement", None))
        part = attrs.get("part", getattr(self.instance, "part", None))
        if part and part.arrangement_id != arrangement.pk:
            raise serializers.ValidationError(
                gettext("Die Stimme gehört zu einem anderen Arrangement.")
            )
        if attrs.get("document", getattr(self.instance, "document", None)) is None:
            raise serializers.ValidationError(
                gettext("Bitte eine zugängliche Notenunterlage wählen.")
            )
        return attrs


class PieceViewSet(MusicViewSet):
    serializer_class = MusicPieceSerializer


class ArrangementViewSet(MusicViewSet):
    serializer_class = MusicArrangementSerializer


class ScorePartViewSet(MusicViewSet):
    serializer_class = MusicScorePartSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]

    @transaction.atomic
    def perform_update(self, serializer):
        # Ausgaben ändern die Leihzeilen, nicht die Bestandszeile selbst.
        # Deshalb nach ihrer Sperre immer erneut gegen die Leihsummen prüfen.
        self._lock_and_refresh(serializer.instance)
        serializer = self._revalidate(serializer)
        super().perform_update(serializer)


class ScoreDocumentViewSet(MusicViewSet):
    serializer_class = MusicScoreDocumentSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]

    def get_queryset(self):
        return super().get_queryset().filter(document__in=visible_documents(self))

    @action(detail=False, methods=["get"])
    def documents(self, request, org_id):
        return Response(list(visible_documents(self).order_by("title", "pk").values("id", "title")))

    @action(detail=True, methods=["get"])
    def download(self, request, org_id, pk):
        link = self.get_object()
        version = link.document.versions.order_by("-uploaded_at", "-pk").first()
        if not version:
            raise NotFound()
        return file_response(request, version)


def voice(instrument, register):
    return instrument.strip().casefold(), register.strip().casefold()


def program_data(performance):
    positions = performance.positions.all()
    planned = Counter()
    accepted = Counter()
    for p in positions:
        planned[voice(p.instrument, p.register)] += p.required
    for a in performance.assignments.filter(
        status="accepted", musician__active=True
    ).select_related("position"):
        accepted[voice(a.position.instrument, a.position.register)] += 1
    entries, preparation = [], []
    seen = set()
    for entry in performance.program_entries.select_related("arrangement__piece"):
        arrangement = entry.arrangement
        duration = (
            entry.duration_seconds
            if entry.duration_seconds is not None
            else arrangement.duration_seconds
            if arrangement
            else 0
        )
        entries.append(
            {
                "id": entry.pk,
                "position": entry.position,
                "kind": entry.kind,
                "arrangement": entry.arrangement_id,
                "title": arrangement.piece.title if arrangement else gettext("Pause"),
                "arrangement_name": arrangement.name if arrangement else "",
                "duration_seconds": entry.duration_seconds,
                "effective_seconds": duration,
                "paper_format": entry.paper_format,
                "note": entry.note,
            }
        )
        if not arrangement or (arrangement.pk, entry.paper_format) in seen:
            continue
        seen.add((arrangement.pk, entry.paper_format))
        groups = {}
        for part in arrangement.parts.all():
            key = (*voice(part.instrument, part.register), part.kind)
            row = groups.setdefault(
                key,
                {
                    "instrument": part.instrument,
                    "register": part.register,
                    "kind": part.kind,
                    "required": 0,
                    "copies": 0,
                    "locations": [],
                },
            )
            row["required"] = max(
                row["required"], part.required_players if part.kind == "part" else 1
            )
            if part.paper_format == entry.paper_format:
                loaned = part.loans.aggregate(n=Sum(F("quantity") - F("returned")))["n"] or 0
                held = (
                    part.loans.filter(
                        musician__assignment__performance=performance,
                        musician__assignment__status__in=["pending", "accepted"],
                        musician__active=True,
                    ).aggregate(n=Sum(F("quantity") - F("returned")))["n"]
                    or 0
                )
                row.setdefault("loaned", 0)
                row.setdefault("held", 0)
                row["loaned"] += loaned
                row["held"] += held
                row["copies"] += part.copies
                if part.location:
                    row["locations"].append(part.location)
        checks = []
        for key, row in groups.items():
            count = accepted[key[:2]] if row["kind"] == "part" else 0
            plan = planned[key[:2]] if row["kind"] == "part" else 0
            need = max(row["required"], plan, count)
            checks.append(
                {
                    **row,
                    "planned": plan,
                    "accepted": count,
                    "missing_players": max(0, row["required"] - count)
                    if row["kind"] == "part"
                    else 0,
                    "missing_planned": max(0, row["required"] - plan)
                    if row["kind"] == "part"
                    else 0,
                    "needed_copies": need,
                    "loaned": row.get("loaned", 0),
                    "available": row["copies"] - row.get("loaned", 0),
                    "held": row.get("held", 0),
                    "missing_copies": max(
                        0, need - row["copies"] + row.get("loaned", 0) - row.get("held", 0)
                    ),
                }
            )
        preparation.append(
            {
                "arrangement": arrangement.pk,
                "name": arrangement.name,
                "title": arrangement.piece.title,
                "paper_format": entry.paper_format,
                "active": arrangement.active,
                "license_note": arrangement.license_note,
                "missing_specification": not any(
                    r["kind"] == "part" and r["required"] for r in checks
                ),
                "voices": checks,
            }
        )
    return {
        "entries": entries,
        "preparation": preparation,
        "total_seconds": sum(e["effective_seconds"] for e in entries),
        "regular_seconds": sum(e["effective_seconds"] for e in entries if e["kind"] != "encore"),
        "encore_seconds": sum(e["effective_seconds"] for e in entries if e["kind"] == "encore"),
    }


class ProgramInput(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, required=False)
    arrangement = serializers.IntegerField(min_value=1, allow_null=True)
    kind = serializers.ChoiceField(choices=["piece", "pause", "encore"])
    duration_seconds = serializers.IntegerField(min_value=0, max_value=86400, allow_null=True)
    paper_format = serializers.ChoiceField(choices=["concert", "march"])
    note = serializers.CharField(max_length=500, allow_blank=True, default="")


class ProgramView(OrgScopedMixin, APIView):
    read_permission = "music.view"
    write_permission = "music.edit"
    allowed_org_types = ("club", "federation")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules or "events" not in self.org.enabled_modules:
            raise NotFound()
        if "events.view" not in self.org_permissions:
            raise PermissionDenied()

    def performance(self, pk):
        qs = (
            Performance.objects.select_for_update()
            if self.request.method == "POST"
            else Performance.objects.all()
        )
        obj = get_object_or_404(qs, pk=pk, organization=self.org)
        if not PerformanceViewSet.visible(self, obj):
            raise NotFound()
        return obj

    def get(self, request, org_id, pk):
        performance = self.performance(pk)
        data = program_data(performance)
        export = request.query_params.get("export")
        if export not in ("program", "parts"):
            return Response(data)
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")

        def write(values):
            writer.writerow(
                [
                    "'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v
                    for v in values
                ]
            )

        if export == "program":
            write(
                [
                    gettext("Reihenfolge"),
                    gettext("Titel"),
                    gettext("Arrangement"),
                    gettext("Art"),
                    gettext("Dauer in Sekunden"),
                    gettext("Hinweis"),
                ]
            )
            for e in data["entries"]:
                write(
                    [
                        e["position"],
                        e["title"],
                        e["arrangement_name"],
                        {
                            "piece": gettext("Stück"),
                            "pause": gettext("Pause"),
                            "encore": gettext("Zugabe"),
                        }[e["kind"]],
                        e["effective_seconds"],
                        e["note"],
                    ]
                )
        else:
            write(
                [
                    gettext("Arrangement"),
                    gettext("Format"),
                    gettext("Instrument"),
                    gettext("Register / Stimme"),
                    gettext("Benötigte Exemplare"),
                    gettext("Vorhandene Exemplare"),
                    gettext("Ausgegeben"),
                    gettext("Freie Exemplare"),
                    gettext("Bei Eingeteilten"),
                    gettext("Fehlende Exemplare"),
                    gettext("Lagerort"),
                    gettext("Lizenzhinweise"),
                ]
            )
            for p in data["preparation"]:
                for v in p["voices"]:
                    write(
                        [
                            p["name"],
                            p["paper_format"],
                            v["instrument"],
                            v["register"],
                            v["needed_copies"],
                            v["copies"],
                            v["loaned"],
                            v["available"],
                            v["held"],
                            v["missing_copies"],
                            ", ".join(v["locations"]),
                            p["license_note"],
                        ]
                    )
        response = HttpResponse("\ufeff" + buf.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{export}-{performance.pk}.csv"'
        response["Cache-Control"] = "private, no-store"
        return response

    @transaction.atomic
    def post(self, request, org_id, pk):
        performance = self.performance(pk)
        entries = performance.program_entries
        action = request.data.get("action", "save")
        if action == "reorder":
            ids = serializers.ListField(
                child=serializers.IntegerField(min_value=1), max_length=1000
            ).run_validation(request.data.get("ids"))
            if len(set(ids)) != len(ids) or set(ids) != set(entries.values_list("pk", flat=True)):
                raise serializers.ValidationError(
                    gettext("Bitte alle Programmpunkte genau einmal anordnen.")
                )
            for index, entry_id in enumerate(ids, 1):
                entries.filter(pk=entry_id).update(position=index)
            record(
                self.org, request.user, "update", performance, {"Programmreihenfolge": [None, ids]}
            )
        elif action == "delete":
            entry_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("id"))
            entry = get_object_or_404(entries, pk=entry_id)
            record(self.org, request.user, "delete", entry, {"Programmpunkt": [entry.pk, None]})
            entry.delete()
        elif action == "save":
            serializer = ProgramInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = dict(serializer.validated_data)
            entry_id = values.pop("id", None)
            arrangement_id = values.pop("arrangement")
            if (values["kind"] == "pause") != (arrangement_id is None) or (
                values["kind"] == "pause" and values["duration_seconds"] is None
            ):
                raise serializers.ValidationError(
                    gettext("Stücke benötigen ein Arrangement, Pausen eine Dauer.")
                )
            arrangement = (
                get_object_or_404(Arrangement, organization=self.org, pk=arrangement_id)
                if arrangement_id
                else None
            )
            if arrangement and not arrangement.active:
                raise serializers.ValidationError(gettext("Dieses Arrangement ist archiviert."))
            entry = (
                get_object_or_404(entries, pk=entry_id)
                if entry_id
                else ProgramEntry(
                    organization=self.org, performance=performance, position=entries.count() + 1
                )
            )
            for key, value in values.items():
                setattr(entry, key, value)
            entry.arrangement = arrangement
            entry.save()
            record(
                self.org,
                request.user,
                "update" if entry_id else "create",
                entry,
                {"Programmpunkt": [None, {**values, "arrangement": arrangement_id}]},
            )
        else:
            raise serializers.ValidationError(gettext("Unbekannte Programmänderung."))
        for index, entry in enumerate(entries.all(), 1):
            if entry.position != index:
                entries.filter(pk=entry.pk).update(position=index)
        return Response(program_data(performance))
