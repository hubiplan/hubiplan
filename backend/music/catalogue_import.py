"""Bounded catalogue imports with a signed preview and no implicit stock updates."""

import csv
import hashlib
import io
import json

from django.core import signing
from django.db import transaction
from django.http import HttpResponse
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.api_base import OrgScopedMixin
from organizations.models import Organization

from .models import Arrangement, Piece, ScorePart

HEADERS = [
    "title",
    "composer",
    "arrangement",
    "arranger",
    "publisher",
    "duration_seconds",
    "difficulty",
    "ensemble",
    "license_note",
    "instrument",
    "register",
    "kind",
    "paper_format",
    "required_players",
    "copies",
    "location",
]
SALT = "music.catalogue.preview.v1"


def text(length, **kwargs):
    return serializers.CharField(max_length=length, allow_blank=True, default="", **kwargs)


class Row(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    composer = text(200)
    arrangement = serializers.CharField(max_length=200)
    arranger = text(200)
    publisher = text(200)
    duration_seconds = serializers.IntegerField(min_value=0, max_value=86400, default=0)
    difficulty = text(100)
    ensemble = text(200)
    license_note = text(2000)
    instrument = text(100)
    register = text(100)
    kind = serializers.ChoiceField(choices=["part", "score"], default="part")
    paper_format = serializers.ChoiceField(choices=["concert", "march"], default="concert")
    required_players = serializers.IntegerField(min_value=0, max_value=500, default=1)
    copies = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    location = text(300)


def normalize(value):
    return value.strip().casefold() if isinstance(value, str) else value


def plan(org, raw):
    """Return immutable operations. Preview performs no database writes."""
    rows = []
    errors = []
    try:
        content = raw.decode("utf-8-sig")
        if "\0" in content:
            raise ValueError()
        delimiter = ";" if ";" in content.splitlines()[0] else ","
        reader = csv.DictReader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)
        columns = reader.fieldnames or []
        if (
            len(columns) != len(set(columns))
            or not {"title", "arrangement"} <= set(columns)
            or set(columns) - set(HEADERS)
        ):
            raise ValueError()
        for number, source in enumerate(reader, 2):
            if number > 1001 or None in source or None in source.values():
                raise ValueError()
            data = {k: v.strip() for k, v in source.items() if v.strip()}
            serializer = Row(data=data)
            if serializer.is_valid():
                rows.append((number, dict(serializer.validated_data)))
            else:
                errors.append(
                    gettext("Zeile {number}: {error}").format(
                        number=number, error=dict(serializer.errors)
                    )
                )
    except (UnicodeDecodeError, csv.Error, ValueError, IndexError):
        errors.append(
            gettext(
                "Bitte eine gültige UTF-8-CSV mit Titel und Arrangement "
                "sowie höchstens 1000 Zeilen wählen."
            )
        )
    if not rows and not errors:
        errors.append(gettext("Die Importdatei enthält keine Noteneinträge."))
    models = {"pieces": Piece, "arrangements": Arrangement, "parts": ScorePart}
    fields = {
        "pieces": ["title", "composer"],
        "arrangements": [
            "piece_id",
            "name",
            "arranger",
            "publisher",
            "duration_seconds",
            "difficulty",
            "ensemble",
            "license_note",
        ],
        "parts": [
            "arrangement_id",
            "instrument",
            "register",
            "kind",
            "paper_format",
            "required_players",
            "copies",
            "location",
        ],
    }
    identities = {
        "pieces": ["title", "composer"],
        "arrangements": ["piece_id", "name"],
        "parts": ["arrangement_id", "instrument", "register", "kind", "paper_format", "location"],
    }
    existing = {
        kind: list(
            model.objects.filter(organization=org)
            .order_by("pk")
            .values("id", *fields[kind], *(["active"] if kind == "arrangements" else []))
        )
        for kind, model in models.items()
    }
    revision = hashlib.sha256(json.dumps(existing, sort_keys=True).encode()).hexdigest()
    maps = {kind: {} for kind in models}
    for kind, items in existing.items():
        for item in items:
            identity = tuple(normalize(item[k]) for k in identities[kind])
            maps[kind].setdefault(identity, []).append(item)
    operations = []
    skipped = 0

    def add(kind, values):
        identity = tuple(normalize(values[k]) for k in identities[kind])
        found = maps[kind].get(identity, [])
        if len(found) > 1:
            raise ValueError(
                gettext("Mehrdeutiger vorhandener Katalogeintrag; bitte zuerst bereinigen.")
            )
        if found:
            other = found[0]
            if any(values[k] != other[k] for k in fields[kind] if k not in identities[kind]):
                raise ValueError(
                    gettext(
                        "Vorhandene Angaben oder Bestände weichen ab; es wird nichts überschrieben."
                    )
                )
            return other["id"]
        identifier = -len(operations) - 1
        operations.append((kind, identifier, values))
        maps[kind][identity] = [{"id": identifier, **values}]
        return identifier

    for number, values in rows:
        before = len(operations)
        try:
            piece = add("pieces", {k: values[k] for k in fields["pieces"]})
            arrangement = add(
                "arrangements",
                {
                    "piece_id": piece,
                    "name": values["arrangement"],
                    **{
                        k: values[k]
                        for k in fields["arrangements"]
                        if k not in ["piece_id", "name"]
                    },
                },
            )
            if values["instrument"]:
                add(
                    "parts",
                    {
                        "arrangement_id": arrangement,
                        **{k: values[k] for k in fields["parts"] if k != "arrangement_id"},
                    },
                )
            elif any(values[k] for k in ["register", "location", "copies"]):
                raise ValueError(gettext("Für einen Stimmenbestand bitte ein Instrument angeben."))
            if before == len(operations):
                skipped += 1
        except ValueError as exc:
            errors.append(gettext("Zeile {number}: {error}").format(number=number, error=str(exc)))
    counts = {kind: sum(k == kind for k, _, _ in operations) for kind in models}
    return (
        {"valid": not errors, "errors": errors[:20], "counts": counts, "skipped": skipped},
        operations,
        revision,
    )


class CatalogueImportView(OrgScopedMixin, APIView):
    read_permission = "scores.view"
    write_permission = "scores.edit"
    allowed_org_types = ("club", "federation")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "scores" not in self.org.enabled_modules:
            raise NotFound()

    def get(self, request, org_id):
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(HEADERS)
        writer.writerow(
            [
                "Musterstück",
                "A. Beispiel",
                "Konzertfassung",
                "",
                "",
                "240",
                "",
                "Blasorchester",
                "Nutzung prüfen",
                "Tuba",
                "",
                "part",
                "concert",
                "1",
                "2",
                "Schrank A",
            ]
        )
        response = HttpResponse(
            "\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="noten-import.csv"'
        response["Cache-Control"] = "private, no-store"
        return response

    @transaction.atomic
    def post(self, request, org_id):
        upload = request.FILES.get("file")
        if not upload or upload.size > 2 * 1024 * 1024:
            raise serializers.ValidationError(
                gettext("Bitte eine CSV-Datei mit höchstens 2 MB wählen.")
            )
        raw = upload.read(2 * 1024 * 1024 + 1)
        digest = hashlib.sha256(raw).hexdigest()
        action = serializers.ChoiceField(choices=["preview", "import"]).run_validation(
            request.data.get("action")
        )
        key = None
        if action == "import":
            if request.data.get("digest") != digest:
                raise serializers.ValidationError(
                    gettext("Die Datei hat sich geändert. Bitte die Vorschau neu erstellen.")
                )
            key = idempotency.claim(request, f"music.catalogue.{org_id}", required=True)
            if key.done:
                return Response(key.result)
        Organization.objects.select_for_update().get(pk=self.org.pk)
        result, operations, revision = plan(self.org, raw)
        if action == "preview":
            if result["valid"]:
                result.update(
                    digest=digest, preview=signing.dumps([org_id, digest, revision], salt=SALT)
                )
            return Response(result)
        try:
            preview = serializers.CharField(max_length=4096).run_validation(
                request.data.get("preview")
            )
            previous = signing.loads(preview, salt=SALT, max_age=1800)
            if previous != [org_id, digest, revision]:
                raise signing.BadSignature()
        except signing.BadSignature as exc:
            raise serializers.ValidationError(
                gettext("Datei oder Katalog haben sich geändert. Bitte die Vorschau neu erstellen.")
            ) from exc
        if not result["valid"]:
            raise serializers.ValidationError(result["errors"])
        ids = {}
        models = {"pieces": Piece, "arrangements": Arrangement, "parts": ScorePart}
        for kind, identifier, values in operations:
            values = dict(values)
            for field in ["piece_id", "arrangement_id"]:
                if values.get(field, 0) < 0:
                    values[field] = ids[values[field]]
            obj = models[kind].objects.create(organization=self.org, **values)
            ids[identifier] = obj.pk
            record(self.org, request.user, "create", obj, {"Katalogimport": [None, True]})
        key.remember(result)
        return Response(result)
