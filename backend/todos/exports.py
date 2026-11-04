from contextlib import contextmanager
from contextvars import ContextVar

from rest_framework.exceptions import NotFound, PermissionDenied

from core.tenancy import tenant_context

from .access import scope_for, visible

_actor = ContextVar("todo_export_actor", default=None)


@contextmanager
def for_actor(user):
    token = _actor.set(user)
    try:
        yield
    finally:
        _actor.reset(token)


def shared_rows(org, department=None):
    from .models import Todo

    user = _actor.get()
    if user is None or not user.is_active:
        return Todo.objects.none()
    # IDs unter der heutigen Aufgabenprüfung bestimmen, erst danach exportieren.
    with tenant_context(org.pk, user.pk):
        try:
            scope = scope_for(user, org.pk, department.pk if department else None)
        except (NotFound, PermissionDenied):
            return Todo.objects.none()
        ids = list(visible(user, scope).filter(shared=True).values_list("pk", flat=True))
    return Todo.objects.filter(organization=org, shared=True, pk__in=ids)


def attachment_rows(org, department=None):
    from .models import TodoAttachment

    return TodoAttachment.objects.filter(todo__in=shared_rows(org, department))


def series_rows(org, department=None):
    from .models import TodoSeries

    return TodoSeries.objects.filter(
        organization=org, pk__in=shared_rows(org, department).values("series_id")
    )


def export_scope(org, department=None):
    user = _actor.get()
    if user is None:
        return None
    with tenant_context(org.pk, user.pk):
        try:
            return scope_for(user, org.pk, department.pk if department else None)
        except (NotFound, PermissionDenied):
            return None


def personal_export(user, include_files=False):
    import json
    import tempfile
    import zipfile

    from django.core.serializers.json import DjangoJSONEncoder
    from django.http import FileResponse, JsonResponse

    from access.permissions import organizations_for
    from core.tenancy import user_view
    from portal.services import department_contexts

    from .attachments import attachment_rows, document_for, row_data
    from .models import Todo, TodoPreference, TodoReminderConfig

    rows = []
    seen = set()
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) if include_files else None
    archive = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) if output else None

    def add(todo, scope):
        if todo.pk in seen:
            return
        seen.add(todo.pk)
        from .series_views import series_data

        row = {
            key: getattr(todo, key)
            for key in (
                "id",
                "title",
                "description",
                "local_note",
                "due_date",
                "due_time",
                "timezone",
                "status",
                "done_at",
                "deleted_at",
                "shared",
                "organization_id",
                "department_id",
            )
        }
        row["local_note"] = todo.local_note if todo.distributed else ""
        row["attachments"] = []
        row["series"] = series_data(todo)
        with attachment_rows(todo, scope) as attachments:
            for attachment, central, aid in attachments:
                item = row_data(attachment, central, aid, scope)
                if archive and item["available"]:
                    if attachment.kind == "file":
                        file, name = attachment.file, attachment.name
                    else:
                        doc = document_for(attachment, scope)
                        version = doc.versions.first() if doc else None
                        file, name = (version.file, version.name) if version else (None, "")
                    if file:
                        from documents.services import storage_name

                        path = f"files/{todo.pk}/{attachment.pk}/{storage_name(name)}"
                        with file.open("rb") as source, archive.open(path, "w") as target:
                            import shutil

                            shutil.copyfileobj(source, target, 1024 * 1024)
                        item["file"] = path
                row["attachments"].append(item)
        config = (
            TodoReminderConfig.objects.filter(todo=todo, user=user)
            .values("days", "enabled", "mail", "push")
            .first()
        )
        row["reminders"] = config
        rows.append(row)

    try:
        with user_view(user.pk):
            for todo in Todo.objects.filter(created_by=user, shared=False, withdrawn=False):
                # Eigene Dateien bleiben auch ohne Rollen zugänglich; Dokumentrechte nicht.
                with tenant_context(todo.organization_id, user.pk):
                    try:
                        scope = scope_for(user, todo.organization_id, todo.department_id)
                    except (NotFound, PermissionDenied):
                        scope = None
                if scope is None:
                    with user_view(user.pk):
                        add(todo, None)
                else:
                    with tenant_context(todo.organization_id, user.pk):
                        scope_for(user, todo.organization_id, todo.department_id)
                        add(todo, scope)
            contexts = [(org.pk, None) for org, _ in organizations_for(user)]
            contexts += [(c.club.pk, c.department.pk) for c in department_contexts(user).values()]
            preferences = (
                TodoPreference.objects.filter(user=user)
                .values(
                    "share_mail",
                    "share_push",
                    "reminder_mail",
                    "reminder_push",
                    "push_title",
                    "purge_done",
                )
                .first()
            )
        for org_id, dept_id in contexts:
            with tenant_context(org_id, user.pk):
                try:
                    scope = scope_for(user, org_id, dept_id)
                except (NotFound, PermissionDenied):
                    continue
                for deleted in (False, True):
                    for todo in visible(user, scope, deleted=deleted).filter(shared=True):
                        add(todo, scope)
        payload = {"tasks": rows, "preferences": preferences}
        if archive:
            archive.writestr(
                "aufgaben.json", json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False)
            )
            archive.close()
            output.seek(0)
            return FileResponse(
                output, as_attachment=True, filename="aufgaben.zip", content_type="application/zip"
            )
        response = JsonResponse(payload)
        response["Content-Disposition"] = 'attachment; filename="aufgaben.json"'
        return response
    except Exception:
        if archive:
            archive.close()
        if output:
            output.close()
        raise
