"""Aufgaben über bestätigte Instanzenkopplungen; kein Durchgriff auf fremde Mandanten."""

import base64
import hashlib
import tempfile

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext, gettext_lazy
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied

from changes.tracking import suppress
from core.tenancy import rls_bypass, tenant_context
from peering import services, transport
from peering.models import Coupling

from .models import Todo, TodoRemoteShare, TodoRemoteTask, TodoSeries
from .views import TodoInput

LIMIT = 100
CHUNK = 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
CENTRAL = ("title", "description", "due_date", "due_time", "timezone")
RULE = (
    "repeat",
    "interval",
    "basis",
    "last_day",
    "ends_on",
    "count",
    "anchor_date",
    "due_time",
    "timezone",
)


class RemoteUnavailable(APIException):
    status_code = 503
    default_detail = gettext_lazy(
        "Die Quellinstanz ist gerade nicht verfügbar. Bitte später erneut versuchen."
    )


def usable(coupling, outgoing=False):
    return (
        coupling.state == Coupling.State.ACTIVE
        and not coupling.peer.pending_keys
        and bool(coupling.level("todos") if outgoing else services.accepted(coupling).get("todos"))
    )


def selected(coupling, uid, *, complete=False):
    if not usable(coupling, outgoing=True):
        raise services.Refused(403, "Aufgabenfreigabe nicht aktiv.")
    share = (
        TodoRemoteShare.objects.filter(
            coupling=coupling, organization_id=coupling.local_unit_id, todo_id=uid, active=True
        )
        .select_related("todo")
        .first()
    )
    if share is None or share.todo.deleted_at or share.todo.withdrawn or not share.todo.shared:
        raise services.Refused(404, "Aufgabe nicht verfügbar.")
    if complete and (share.mode != "common" or not share.can_complete or share.todo.per_unit):
        raise services.Refused(403, "Erledigung nicht freigegeben.")
    return share


def source_files(share):
    from rest_framework.exceptions import NotFound

    from .access import scope_for
    from .attachments import document_for

    todo = share.todo
    scope = None
    if todo.owner_id:
        with tenant_context(todo.organization_id, todo.owner_id):
            try:
                scope = scope_for(todo.owner, todo.organization_id, todo.department_id)
            except (NotFound, PermissionDenied):
                pass
    for attachment in todo.attachments.filter(deleted_at__isnull=True).order_by("pk"):
        if attachment.kind == "document":
            with tenant_context(todo.organization_id, todo.owner_id):
                document = document_for(attachment, scope)
                version = document.versions.first() if document else None
            if not version:
                continue
            yield attachment, version.file, version.name, version.file.size, True
        else:
            yield attachment, attachment.file, attachment.name, attachment.size, False


def snapshot(share):
    todo = share.todo
    values = {key: getattr(todo, key) for key in CENTRAL}
    rule = None
    if todo.series_id and share.following:
        series = todo.series
        rule = {key: getattr(series, key) for key in RULE}
        rule.update({"uid": str(series.pk), "active": series.active and not series.deleted_at})
        if share.mode == "copy":
            # Künftige Inhalte sind nur mit ausdrücklicher Serienfreigabe autorisiert.
            values.update(title=series.title, description=series.description)
    return {
        "uid": str(todo.pk),
        "version": todo.version,
        "revision": share.revision,
        "mode": share.mode,
        "can_complete": share.can_complete,
        "following": share.following,
        "status": todo.status,
        "done_at": todo.done_at.isoformat() if todo.done_at else None,
        "sequence_no": todo.sequence_no,
        "series": rule,
        **{
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in values.items()
        },
        "files": [
            {"id": a.pk, "name": name, "size": size, "future": future}
            for a, _, name, size, future in source_files(share)
        ],
    }


class SnapshotInput(serializers.Serializer):
    uid = serializers.RegexField(r"^[1-9][0-9]{0,18}$")
    version = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=1)
    mode = serializers.ChoiceField(choices=["copy", "common"])
    can_complete = serializers.BooleanField(default=True)
    following = serializers.BooleanField(default=False)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=50000, allow_blank=True)
    due_date = serializers.DateField(allow_null=True)
    due_time = serializers.TimeField(allow_null=True)
    timezone = serializers.CharField(max_length=64)
    status = serializers.ChoiceField(choices=["open", "done"])
    done_at = serializers.DateTimeField(allow_null=True)
    sequence_no = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    series = serializers.JSONField(allow_null=True, required=False)
    files = serializers.ListField(child=serializers.DictField(), max_length=200, default=list)

    def validate(self, attrs):
        check = TodoInput(data={key: attrs[key] for key in CENTRAL})
        check.is_valid(raise_exception=True)
        if attrs["due_time"] and not attrs["due_date"]:
            raise serializers.ValidationError("Uhrzeit ohne Datum.")
        for f in attrs["files"]:
            if (
                set(f) != {"id", "name", "size", "future"}
                or type(f["id"]) is not int
                or f["id"] <= 0
                or type(f["size"]) is not int
                or not 0 <= f["size"] <= MAX_FILE
                or not isinstance(f["name"], str)
                or len(f["name"]) > 200
                or type(f["future"]) is not bool
            ):
                raise serializers.ValidationError("Ungültiger Aufgabendateieintrag.")
        if attrs.get("series") is not None:
            from .series_views import SeriesInput

            rule = attrs["series"]
            if (
                not isinstance(rule, dict)
                or set(rule) != {*RULE, "uid", "active"}
                or not str(rule.get("uid", "")).isdigit()
                or type(rule.get("active")) is not bool
            ):
                raise serializers.ValidationError("Ungültige Serienregel.")
            test = SeriesInput(
                data={"version": 1, **{key: rule[key] for key in RULE if key in rule}}
            )
            test.is_valid(raise_exception=True)
            if "repeat" not in test.validated_data or rule.get("timezone") != attrs["timezone"]:
                raise serializers.ValidationError("Ungültige Serienregel.")
            from django.utils.dateparse import parse_date

            if not rule.get("anchor_date") or not parse_date(str(rule["anchor_date"])):
                raise serializers.ValidationError("Ungültiger Serienanker.")
        return attrs


def build(coupling, level):
    with rls_bypass():
        rows = (
            TodoRemoteShare.objects.filter(
                coupling=coupling,
                organization_id=coupling.local_unit_id,
                active=True,
                todo__deleted_at__isnull=True,
                todo__withdrawn=False,
                todo__shared=True,
            )
            .select_related("todo", "todo__series")
            .order_by("pk")[:LIMIT]
        )
        return {"items": [snapshot(row) for row in rows]}


def _serialize(values):
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def apply(coupling, data):
    items = data.get("items", []) if data.get("level") else []
    if not isinstance(items, list) or len(items) > LIMIT:
        raise serializers.ValidationError("Zu viele Verbundaufgaben.")
    validated = SnapshotInput(data=items, many=True)
    validated.is_valid(raise_exception=True)
    with suppress(), rls_bypass():
        keep = []
        for values in validated.validated_data:
            mapping = receive_one(coupling, _serialize(values))
            keep.append(mapping.pk)
        for mapping in TodoRemoteTask.objects.filter(
            coupling=coupling, pk__in=keep, todo__isnull=True
        ):
            adopt_successor(mapping)
        for mapping in TodoRemoteTask.objects.filter(coupling=coupling, active=True).exclude(
            pk__in=keep
        ):
            mapping.active = False
            mapping.save(update_fields=["active"])
            TodoSeries.objects.filter(occurrences__remote_origin=mapping).update(active=False)
            if mapping.mode == "common":
                Todo.objects.filter(remote_origin=mapping).update(
                    withdrawn=True, version=F("version") + 1
                )


@transaction.atomic
def receive_one(coupling, item):
    mapping, created = TodoRemoteTask.objects.select_for_update().get_or_create(
        coupling=coupling,
        uid=item["uid"],
        defaults={"organization_id": coupling.local_unit_id, "mode": item["mode"]},
    )
    if not created and (
        item["revision"] < mapping.share_revision
        or item["revision"] == mapping.share_revision
        and item["version"] < mapping.source_version
    ):
        return mapping
    if mapping.todo_id and item["mode"] != mapping.mode:
        raise serializers.ValidationError(
            "Die Verteilart einer übernommenen Aufgabe ist unveränderlich."
        )
    if not created and mapping.active and mapping.payload == item:
        return mapping
    was_active = mapping.active
    mapping.payload = item
    mapping.active = True
    mapping.source_version = item["version"]
    mapping.share_revision = item["revision"]
    mapping.mode = item["mode"]
    mapping.remote_series_uid = str((item.get("series") or {}).get("uid", ""))
    mapping.received_at = timezone.now()
    mapping.save()
    if mapping.todo_id:
        rows = Todo.objects.filter(remote_origin=mapping)
        if was_active:
            rows = rows.filter(withdrawn=False)
        for todo in rows:
            if mapping.mode == "copy" and todo.status == "done":
                continue
            if not was_active and mapping.mode == "common":
                todo.withdrawn = False
            for key in CENTRAL:
                if (
                    key == "due_date"
                    and mapping.mode == "copy"
                    and todo.series_id
                    and (todo.sequence_no or 1) > 1
                ):
                    continue
                value = item[key]
                if key == "due_date":
                    from django.utils.dateparse import parse_date

                    value = parse_date(value) if value else None
                if key == "due_time":
                    from django.utils.dateparse import parse_time

                    value = parse_time(value) if value else None
                setattr(todo, key, value)
            if mapping.mode == "common":
                todo.status = item["status"]
                todo.done_at = parse_datetime(item["done_at"]) if item.get("done_at") else None
                todo.done_by = None
            todo.version += 1
            todo.due_revision += 1
            todo.save()
            if todo.series_id and item.get("series"):
                update_local_rule(todo.series, item["series"])
            elif todo.series_id:
                TodoSeries.objects.filter(pk=todo.series_id).update(active=False)
    return mapping


def update_local_rule(series, rule):
    from django.utils.dateparse import parse_date, parse_time

    for key in RULE:
        if key in rule:
            value = rule[key]
            if key in {"anchor_date", "ends_on"}:
                value = parse_date(value) if value else None
            elif key == "due_time":
                value = parse_time(value) if value else None
            setattr(series, key, value)
    series.active = bool(rule.get("active")) and not series.locally_stopped
    series.version += 1
    series.save()


def completion_allowed(todo):
    if not todo.remote_origin_id:
        return not todo.remote_mode
    return bool(todo.remote_origin.payload.get("can_complete"))


def fresh_rows(rows):
    """Keine veralteten gemeinsamen Inhalte ausliefern, wenn die Quelle ausfällt."""
    from rest_framework.exceptions import NotFound

    unavailable = set()
    for todo in rows:
        if todo.remote_mode == "common" and todo.remote_origin_id in unavailable:
            continue
        try:
            yield refresh_common(todo)
        except RemoteUnavailable:
            unavailable.add(todo.remote_origin_id)
            continue
        except NotFound:
            continue


class ProgressInput(serializers.Serializer):
    sequence_no = serializers.IntegerField(min_value=1, max_value=10000)
    due_date = serializers.DateField(allow_null=True)
    status = serializers.ChoiceField(choices=["open", "done"])
    done_at = serializers.DateTimeField(allow_null=True)
    ended = serializers.BooleanField()
    deleted = serializers.BooleanField()


def report_progress(sender, instance, raw=False, **kwargs):
    if raw or instance.remote_mode != "copy" or not instance.remote_origin_id:
        return
    with rls_bypass():
        mapping = instance.remote_origin
        if not mapping.active or not usable(mapping.coupling):
            return
        row = {
            "sequence_no": instance.sequence_no or 1,
            "due_date": instance.due_date,
            "status": instance.status,
            "done_at": instance.done_at,
            "ended": bool(
                instance.series_id and (not instance.series.active or instance.series.deleted_at)
            ),
            "deleted": bool(instance.deleted_at),
        }

        def send():
            with transaction.atomic(), tenant_context(mapping.organization_id), rls_bypass():
                current = (
                    TodoRemoteTask.objects.select_related("coupling__peer")
                    .filter(pk=mapping.pk, active=True)
                    .first()
                )
                if current and usable(current.coupling):
                    services.enqueue(
                        current.coupling,
                        "todo.report",
                        {"uid": current.uid, "progress": _serialize(row)},
                    )

        transaction.on_commit(send)


def receive_report(coupling, data):
    if not isinstance(data.get("uid"), str) or not data["uid"].isdigit() or len(data["uid"]) > 19:
        raise services.Refused(400, "Ungültige Aufgabennummer.")
    with rls_bypass():
        share = selected(coupling, data.get("uid"))
        if share.mode != "copy":
            raise services.Refused(403, "Keine Einzelkopie.")
        check = ProgressInput(data=data.get("progress"))
        check.is_valid(raise_exception=True)
        row = _serialize(check.validated_data)
        progress = [p for p in share.progress if p["sequence_no"] != row["sequence_no"]]
        progress.append(row)
        share.progress = sorted(progress, key=lambda p: p["sequence_no"])[-10000:]
        share.save(update_fields=["progress"])


def inherit_remote_shares(sender, instance, created=False, raw=False, **kwargs):
    if (
        raw
        or not created
        or not instance.series_id
        or not instance.sequence_no
        or instance.remote_origin_id
    ):
        return
    with rls_bypass(), suppress():
        previous = TodoRemoteShare.objects.filter(
            todo__series_id=instance.series_id,
            todo__sequence_no=instance.sequence_no - 1,
            active=True,
            following=True,
            mode="common",
        ).select_related("coupling")
        for share in previous:
            TodoRemoteShare.objects.get_or_create(
                organization=instance.organization,
                todo=instance,
                coupling=share.coupling,
                defaults={"mode": "common", "can_complete": share.can_complete, "following": True},
            )
            Todo.objects.filter(pk=instance.pk).update(shared=True)
            instance.shared = True


def adopt_successor(mapping):
    if mapping.todo_id or mapping.mode != "common" or not mapping.remote_series_uid:
        return
    previous = (
        TodoRemoteTask.objects.filter(
            coupling=mapping.coupling,
            remote_series_uid=mapping.remote_series_uid,
            active=True,
            todo__isnull=False,
        )
        .select_related("todo__owner")
        .order_by("-pk")
        .first()
    )
    if not previous or not previous.payload.get("following") or not previous.todo.owner_id:
        return
    from rest_framework.exceptions import NotFound

    from .access import scope_for

    try:
        with tenant_context(mapping.organization_id, previous.todo.owner_id):
            scope = scope_for(previous.todo.owner, mapping.organization_id)
            todo = adopt(mapping, previous.todo.owner, scope)
            from .models import TodoShare

            with rls_bypass(), suppress():
                for grant in previous.todo.shares.all():
                    grant.pk = None
                    grant.todo = todo
                    grant.save()
                if TodoShare.objects.filter(todo=todo).exists():
                    Todo.objects.filter(pk=todo.pk).update(shared=True)
    except (NotFound, PermissionDenied):
        return


def adopt(mapping, user, scope):
    if (
        mapping.organization_id != scope.org.pk
        or scope.department_id
        or "todos.edit" not in scope.permissions
        or not mapping.active
        or not usable(mapping.coupling)
    ):
        raise PermissionDenied()
    if mapping.todo_id:
        raise PermissionDenied()
    item = mapping.payload
    values = SnapshotInput(data=item)
    values.is_valid(raise_exception=True)
    fields = {key: values.validated_data[key] for key in CENTRAL}
    with suppress(), rls_bypass():
        todo = Todo.objects.create(
            organization=scope.org,
            owner=user,
            created_by=user,
            shared=False,
            distributed=True,
            remote_origin=mapping,
            remote_mode=mapping.mode,
            status=item["status"] if mapping.mode == "common" else "open",
            **fields,
        )
        if mapping.mode == "copy" and item.get("series") and item.get("following"):
            from .series import snapshot_template

            series = TodoSeries(organization=scope.org, owner=user, anchor_date=todo.due_date)
            snapshot_template(todo, series)
            series.title, series.description = todo.title, todo.description
            update_local_rule(series, item["series"])
            todo.series = series
            todo.sequence_no = 1
            todo.save(update_fields=["series", "sequence_no"])
        if mapping.mode == "common" and item.get("done_at"):
            todo.done_at = parse_datetime(item["done_at"])
            todo.save(update_fields=["done_at"])
        mapping.todo = todo
        mapping.save(update_fields=["todo"])
    return todo


def call(mapping, kind, **values):
    coupling = mapping.coupling
    if not mapping.active or not usable(coupling):
        raise RemoteUnavailable()
    try:
        # Auch im Mehrinstanz-Test stellt der Kontextmanager die aufrufende Sicht wieder her.
        with tenant_context(mapping.organization_id):
            return transport.call(
                services.keys_of(coupling.peer),
                "/api/peering/v1/query/",
                {
                    "from_unit": str(coupling.local_unit.uuid),
                    "to_unit": str(coupling.remote_uuid),
                    "kind": kind,
                    "uid": mapping.uid,
                    **values,
                },
            )
    except transport.PeerError as exc:
        raise RemoteUnavailable() from exc


def refresh_common(todo):
    if todo.remote_mode != "common":
        return todo
    if not todo.remote_origin_id:
        raise RemoteUnavailable()
    mapping = todo.remote_origin
    answer = call(mapping, "todo.read")
    if not answer.get("available"):
        with suppress(), rls_bypass():
            TodoRemoteTask.objects.filter(pk=mapping.pk).update(active=False)
            Todo.objects.filter(remote_origin=mapping).update(withdrawn=True)
        from rest_framework.exceptions import NotFound

        raise NotFound()
    check = SnapshotInput(data=answer.get("task"))
    check.is_valid(raise_exception=True)
    if str(check.validated_data["uid"]) != mapping.uid:
        raise RemoteUnavailable()
    with suppress(), rls_bypass():
        receive_one(mapping.coupling, _serialize(check.validated_data))
    todo.refresh_from_db()
    return todo


def complete_common(todo, user, status):
    from .attachments import Conflict

    if not todo.remote_origin_id or todo.remote_mode != "common":
        raise RemoteUnavailable()
    mapping = todo.remote_origin
    answer = call(mapping, "todo.complete", version=mapping.source_version, status=status)
    if answer.get("conflict"):
        raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
    check = SnapshotInput(data=answer.get("task"))
    check.is_valid(raise_exception=True)
    if check.validated_data["uid"] != mapping.uid:
        raise RemoteUnavailable()
    with suppress(), rls_bypass():
        receive_one(mapping.coupling, _serialize(check.validated_data))
    todo.refresh_from_db()
    return todo


def answer(coupling, payload):
    """Nur die von genau dieser Kopplung autorisierte Quelle; keine freie Objektabfrage."""
    if payload.get("kind") not in {"todo.read", "todo.complete", "todo.file"}:
        raise services.Refused(400, "Unbekannte Aufgabenabfrage.")
    uid = payload.get("uid")
    if not str(uid).isdigit() or len(str(uid)) > 19:
        raise services.Refused(400, "Ungültige Aufgabennummer.")
    with transaction.atomic(), suppress(), rls_bypass():
        try:
            share = selected(coupling, uid, complete=payload["kind"] == "todo.complete")
        except services.Refused as exc:
            if payload["kind"] == "todo.read":
                return {"available": False}
            raise exc
        if payload["kind"] == "todo.file":
            return file_chunk(share, payload)
        todo = share.todo
        if payload["kind"] == "todo.complete":
            if type(payload.get("version")) is not int or payload.get("status") not in {
                "open",
                "done",
            }:
                raise services.Refused(400, "Ungültige Aufgabenänderung.")
            if todo.series_id:
                TodoSeries.objects.only("pk").select_for_update().get(pk=todo.series_id)
            todo = Todo.objects.select_for_update().get(pk=todo.pk)
            # Freigabe nach der Aufgabensperre erneut prüfen: gleichzeitig widerrufen
            # darf keine nachträgliche Statusänderung ermöglichen.
            share = selected(coupling, uid, complete=True)
            share.todo = todo
            if todo.version != payload["version"]:
                return {"conflict": True}
            if todo.status != payload["status"]:
                todo.status = payload["status"]
                todo.done_at = timezone.now() if todo.status == "done" else None
                todo.done_by = None
                todo.version += 1
                from django.core.exceptions import ValidationError

                try:
                    todo.save(
                        update_fields=["status", "done_at", "done_by", "version", "updated_at"]
                    )
                    from audit.log import record

                    record(todo.organization, None, "update", todo)
                except ValidationError as exc:
                    raise services.Refused(409, "; ".join(exc.messages)) from exc
        return {"available": True, "task": snapshot(share)}


def file_chunk(share, payload):
    offset, aid = payload.get("offset"), payload.get("attachment")
    if type(offset) is not int or not 0 <= offset <= MAX_FILE or type(aid) is not int:
        raise services.Refused(400, "Ungültiger Dateibereich.")
    row = next((row for row in source_files(share) if row[0].pk == aid), None)
    if row is None:
        raise services.Refused(404, "Datei nicht verfügbar.")
    attachment, file, name, size, _ = row
    if size > MAX_FILE or offset > size:
        raise services.Refused(413, "Datei zu groß.")
    fingerprint = hashlib.sha256(f"{file.name}:{size}".encode()).hexdigest()
    if payload.get("fingerprint") not in (None, fingerprint):
        raise services.Refused(409, "Dateistand geändert.")
    from core.virenscan import release_ok

    release_ok(file, name, "Verbundaufgabe", fingerprint)
    with file.open("rb") as source:
        source.seek(offset)
        content = source.read(CHUNK)
    return {
        "name": name,
        "size": size,
        "fingerprint": fingerprint,
        "data": base64.b64encode(content).decode(),
        "offset": offset,
    }


def remote_file(todo, aid):
    from django.core.files.uploadedfile import UploadedFile
    from django.http import FileResponse

    from core.virenscan import release_ok
    from documents.services import check_upload, clean_name

    mapping = todo.remote_origin
    allowed = [
        f
        for f in mapping.payload.get("files", [])
        if f["id"] == aid and (not todo.sequence_no or todo.sequence_no == 1 or f.get("future"))
    ]
    if not allowed:
        raise PermissionDenied()
    output = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        offset = 0
        fingerprint = None
        while True:
            chunk = call(
                mapping, "todo.file", attachment=aid, offset=offset, fingerprint=fingerprint
            )
            size = chunk.get("size")
            if (
                type(size) is not int
                or not 0 <= size <= MAX_FILE
                or chunk.get("offset") != offset
                or fingerprint is not None
                and chunk.get("fingerprint") != fingerprint
            ):
                raise RemoteUnavailable()
            fingerprint = chunk.get("fingerprint")
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or not isinstance(chunk.get("name"), str)
                or len(chunk["name"]) > 200
            ):
                raise RemoteUnavailable()
            try:
                content = base64.b64decode(chunk["data"], validate=True)
            except (KeyError, ValueError) as exc:
                raise RemoteUnavailable() from exc
            if (
                len(content) > CHUNK
                or not content
                and offset < size
                or offset + len(content) > size
            ):
                raise RemoteUnavailable()
            output.write(content)
            offset += len(content)
            if offset == size:
                break
        output.seek(0)
        upload = UploadedFile(output, name=clean_name(chunk["name"]), size=offset)
        content_type = check_upload(upload)
        # Die Virenprüfung schließt ihren Lesekontext; die Antwort besitzt weiterhin
        # die temporäre Datei und schließt sie nach dem Versand.
        from contextlib import nullcontext

        class ScanFile:
            def open(self, mode):
                output.seek(0)
                return nullcontext(output)

        release_ok(ScanFile(), upload.name, "Verbundaufgabe", fingerprint)
        output.seek(0)
        response = FileResponse(
            output, as_attachment=True, filename=upload.name, content_type=content_type
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        output.close()
        raise


def file_entries(todo):
    if not todo.remote_origin_id:
        return []
    mapping = todo.remote_origin
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "size": f["size"],
            "remote": True,
            "central": True,
            "available": mapping.active and usable(mapping.coupling),
            "deleted_at": None,
            "kind": "file",
        }
        for f in mapping.payload.get("files", [])
        if (todo.sequence_no or 1) == 1 or f.get("future")
    ]
