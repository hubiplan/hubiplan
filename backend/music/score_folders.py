"""Notenmappen: feste Mappen (Marschbuch, Repertoire) und Mappen je Termin für die App.

Die Mappen geben keine eigenen Rechte: Dateien sieht ein Musiker nur, wenn sie zu seiner
Stimme passen und die Dokumentenablage sie für Mitglieder freigibt (wie unter „Meine Noten“).
"""

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import tenant_context
from documents.models import DocumentVersion
from organizations.models import Department
from organizations.tree import UnitTree
from portal.views import _portal_access

from .models import Arrangement, ScoreFolder, ScoreFolderItem, ScoreFolderUnit
from .practice_portal import accessible_scores, own_musician, practice_rows, visible_folders
from .scores import ScoresViewSet
from .views import ScopedSerializer

# Auftritte bleiben so lange nach dem Termin in der App (Konzept E4)
KEEP_AFTER = timedelta(days=7)


class ScoreFolderItemSerializer(ScopedSerializer):
    number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    title = serializers.CharField(source="arrangement.piece.title", read_only=True)
    arrangement_name = serializers.CharField(source="arrangement.name", read_only=True)

    class Meta:
        model = ScoreFolderItem
        fields = ["id", "folder", "arrangement", "position", "number", "title", "arrangement_name"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "number" in attrs:
            attrs["number"] = attrs["number"].strip()
        folder = attrs.get("folder", getattr(self.instance, "folder", None))
        number = attrs.get("number", getattr(self.instance, "number", ""))
        arrangement = attrs.get("arrangement", getattr(self.instance, "arrangement", None))
        others = ScoreFolderItem.objects.filter(folder=folder).exclude(
            pk=getattr(self.instance, "pk", None)
        )
        if number and others.filter(number__iexact=number).exists():
            raise serializers.ValidationError(
                {"number": gettext("Diese Nummer gibt es in der Mappe schon.")}
            )
        if arrangement and others.filter(arrangement=arrangement).exists():
            raise serializers.ValidationError(
                {"arrangement": gettext("Dieses Arrangement steht schon in der Mappe.")}
            )
        return attrs


class ScoreFolderSerializer(ScopedSerializer):
    kind = serializers.ChoiceField(choices=["marchbook", "repertoire", "other"], required=False)
    departments = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=200, required=False
    )
    items = ScoreFolderItemSerializer(many=True, read_only=True)

    class Meta:
        model = ScoreFolder
        fields = ["id", "name", "kind", "position", "departments", "note", "active", "items"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["departments"] = sorted(u.department_id for u in instance.units.all())
        return data

    def validate_departments(self, value):
        org = self.context["view"].org
        found = set(
            Department.objects.filter(organization=org, pk__in=value).values_list("pk", flat=True)
        )
        if found != set(value):
            raise serializers.ValidationError(gettext("Diese Untereinheit gibt es nicht."))
        return sorted(found)

    def _save_units(self, folder, departments):
        if departments is None:
            return
        folder.units.exclude(department_id__in=departments).delete()
        have = set(folder.units.values_list("department_id", flat=True))
        ScoreFolderUnit.objects.bulk_create(
            ScoreFolderUnit(organization=folder.organization, folder=folder, department_id=d)
            for d in departments
            if d not in have
        )

    def create(self, validated_data):
        departments = validated_data.pop("departments", None)
        folder = super().create(validated_data)
        self._save_units(folder, departments)
        return folder

    def update(self, instance, validated_data):
        departments = validated_data.pop("departments", None)
        folder = super().update(instance, validated_data)
        self._save_units(folder, departments)
        return folder


class ScoreFolderViewSet(ScoresViewSet):
    """Feste Notenmappen; Lesen wie der Notenbestand, Schreiben mit Notenarchiv-Recht."""

    serializer_class = ScoreFolderSerializer
    http_method_names = [*ScoresViewSet.http_method_names, "delete"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .order_by("position", "name", "pk")
            .prefetch_related("units", "items__arrangement__piece")
        )

    @action(detail=False, methods=["get"])
    def units(self, request, org_id):
        """Untereinheiten zur Auswahl, wer eine Mappe sieht (ohne Einstellungsrecht)."""
        tree = UnitTree.of(self.org.pk)
        rows = Department.objects.filter(organization=self.org, is_active=True)
        return Response(
            sorted(
                ({"id": d.pk, "name": tree.path(d.pk) or d.name} for d in rows),
                key=lambda r: r["name"].casefold(),
            )
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reorder(self, request, org_id, pk):
        """Reihenfolge der Stücke als Liste von Eintrags-IDs."""
        folder = self.get_object()
        ids = serializers.ListField(
            child=serializers.IntegerField(min_value=1), max_length=2000
        ).run_validation(request.data.get("items"))
        items = {i.pk: i for i in folder.items.select_for_update()}
        if sorted(ids) != sorted(items):
            raise serializers.ValidationError(gettext("Bitte alle Stücke der Mappe angeben."))
        for position, pk in enumerate(ids, start=1):
            if items[pk].position != position:
                items[pk].position = position
                items[pk].save(update_fields=["position"])
        return Response(self.get_serializer(folder).data)


class ScoreFolderItemViewSet(ScoresViewSet):
    serializer_class = ScoreFolderItemSerializer
    http_method_names = [*ScoresViewSet.http_method_names, "delete"]

    def get_queryset(self):
        return super().get_queryset().select_related("arrangement__piece")

    def perform_create(self, serializer):
        folder = serializer.validated_data["folder"]
        if "position" not in self.request.data:
            last = folder.items.aggregate(m=Max("position"))["m"] or 0
            serializer.validated_data["position"] = last + 1
        super().perform_create(serializer)


# --- Mitgliederbereich und App ---


def _latest_versions(document_ids):
    latest = {}
    for v in DocumentVersion.objects.filter(document_id__in=document_ids).order_by(
        "document_id", "-uploaded_at", "-pk"
    ):
        latest.setdefault(v.document_id, v)
    return latest


def _score_rows(access, scores):
    versions = _latest_versions({s.document_id for s in scores})
    by_arrangement = defaultdict(list)
    for s in scores:
        version = versions.get(s.document_id)
        if version is None:
            continue
        by_arrangement[s.arrangement_id].append(
            {
                "id": s.pk,
                "title": s.document.title,
                "instrument": s.part.instrument if s.part_id else "",
                "register": s.part.register if s.part_id else "",
                "part_kind": s.part.kind if s.part_id else "",
                "paper_format": s.part.paper_format if s.part_id else "",
                "usage_note": s.usage_note,
                "position": s.position,
                "version": version.pk,
                "filename": version.name,
                "size": version.size,
                "content_type": version.content_type,
                "uploaded_at": version.uploaded_at,
                "url": f"/api/portal/{access.pk}/music/files/{s.pk}/",
            }
        )
    return by_arrangement


def _piece(arrangement, scores, **extra):
    return {
        "kind": "piece",
        "arrangement": arrangement.pk,
        "title": arrangement.piece.title,
        "composer": arrangement.piece.composer,
        "arrangement_name": arrangement.name,
        "arranger": arrangement.arranger,
        "license_note": arrangement.license_note,
        "duration_seconds": arrangement.duration_seconds,
        "scores": scores.get(arrangement.pk, []),
        **extra,
    }


def _pause(kind, note=""):
    return {
        "kind": kind,
        "arrangement": None,
        "title": gettext("Pause") if kind == "pause" else note,
        "composer": "",
        "arrangement_name": "",
        "arranger": "",
        "license_note": "",
        "duration_seconds": 0,
        "scores": [],
        "note": note,
    }


def folder_data(access, musician):
    practice = practice_rows(musician)
    scores = list(accessible_scores(access, musician, practice))
    rows = _score_rows(access, scores)
    folders = []
    for folder in visible_folders(access, musician).prefetch_related("items__arrangement__piece"):
        folders.append(
            {
                "id": folder.pk,
                "kind": folder.kind,
                "name": folder.name,
                "note": folder.note,
                "items": [
                    _piece(i.arrangement, rows, position=i.position, number=i.number)
                    for i in folder.items.all()
                    if i.arrangement.active
                ],
            }
        )
    events = []
    if "events" in access.organization.enabled_modules:
        since = timezone.now() - KEEP_AFTER
        for a in (
            musician.assignment_set.exclude(status="declined")
            .filter(performance__event__starts_at__gte=since)
            .select_related("performance__event")
            .prefetch_related("performance__program_entries__arrangement__piece")
        ):
            event = a.performance.event
            cancelled = event.is_cancelled
            items = []
            for n, e in enumerate(a.performance.program_entries.all(), start=1):
                if e.arrangement_id:
                    items.append(
                        _piece(
                            e.arrangement,
                            {} if cancelled else rows,
                            position=n,
                            number="",
                            note=e.note,
                            entry_kind=e.kind,
                        )
                    )
                else:
                    items.append({**_pause(e.kind, e.note), "position": n, "number": ""})
            events.append(
                {
                    "key": f"performance-{a.performance_id}",
                    "type": "performance",
                    "title": event.title,
                    "starts_at": event.starts_at,
                    "ends_at": event.ends_at,
                    "location": event.location,
                    "cancelled": cancelled,
                    "items": items,
                }
            )
        rehearsals = [r for r in practice if r["starts_at"] >= since or r["ends_at"] >= since]
        arrangements = Arrangement.objects.filter(
            organization=access.organization,
            pk__in={i["arrangement"] for r in rehearsals for i in r["items"]},
        ).select_related("piece")
        by_id = {a.pk: a for a in arrangements}
        for r in rehearsals:
            usable = not r["cancelled"] and r["status"] != "declined"
            events.append(
                {
                    "key": f"rehearsal-{r['id']}-{r['original_start'].isoformat()}",
                    "type": "rehearsal",
                    "title": r["title"],
                    "starts_at": r["starts_at"],
                    "ends_at": r["ends_at"],
                    "location": r["location"],
                    "cancelled": r["cancelled"],
                    "focus": r["focus"],
                    "items": [
                        _piece(
                            by_id[i["arrangement"]],
                            rows if usable else {},
                            position=n,
                            number="",
                            note=i["focus"],
                        )
                        for n, i in enumerate(r["items"], start=1)
                        if i["arrangement"] in by_id
                    ],
                }
            )
        events.sort(key=lambda e: e["starts_at"])
    return {"folders": folders, "events": events}


class OwnFolders(APIView):
    """Notenmappen des eigenen Musikerprofils (App: Bereich „Noten“)."""

    def get(self, request, access_id):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician:
                return Response({"folders": [], "events": []})
            return Response(folder_data(access, musician))
