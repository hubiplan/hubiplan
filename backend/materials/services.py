import io
import warnings

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import access
from .models import MaterialDocumentLink, MaterialEventLink, MaterialRevision, MaterialTodoLink
from .serializers import EventInput, ItemInput

FIELDS = (
    "title",
    "description",
    "purpose",
    "location_kind",
    "member_id",
    "address",
    "location_note",
    "condition",
    "condition_note",
)


def snapshot(item):
    data = {key: getattr(item, key) for key in FIELDS}
    data["deleted"] = item.deleted_at is not None
    data["events"] = list(
        item.event_links.values(
            "event_id", "kind", "original_start", "valid_from", "valid_until", "note", "rule"
        )
    )
    for row in data["events"]:
        for key in ("original_start", "valid_from", "valid_until"):
            if row[key] is not None:
                row[key] = row[key].isoformat()
    data["todos"] = list(item.todo_links.values_list("todo_id", flat=True))
    data["documents"] = list(item.document_links.values_list("document_id", flat=True))
    data["photo"] = item.photos.filter(deleted_at__isnull=True).values_list("pk", flat=True).first()
    return data


def changed(item, user, before, action):
    MaterialRevision.objects.create(
        organization=item.organization,
        department_id=item.department_id,
        item=item,
        actor=user,
        version=item.version,
        action=action,
        data=before,
    )
    item.version += 1
    item.save()


def expected(item, value):
    # bool ist in Python int; ausdrücklich keine implizite Versionskonvertierung.
    if type(value) is not int or value != item.version:
        from rest_framework.exceptions import APIException

        exc = APIException(_("Das Material wurde inzwischen geändert. Bitte neu laden."))
        exc.status_code = 409
        raise exc


def revision_visible(revision, user, scope):
    if revision.action != "links":
        return True
    # Ein fremder Link-Verlauf könnte schon durch seine Existenz private Aufgaben verraten.
    return revision.actor_id == user.pk


def scope_values(item):
    return {"organization": item.organization, "department_id": item.department_id, "item": item}


def validate_todos(ids, user, scope):
    from todos.access import can_edit

    rows = list(access.todos(user, scope).filter(pk__in=ids))
    if len(rows) != len(set(ids)) or any(not can_edit(r, user, scope) for r in rows):
        raise PermissionDenied()


def restore_snapshot(item, data, user, scope):
    """Rückgängig validiert die heutigen Ziele, einschließlich der zu entfernenden Links."""
    if data["deleted"]:
        ensure_no_music_loan(item)
    payload = {key: data[key] for key in FIELDS if key != "member_id"}
    payload["member"] = data["member_id"]
    form = ItemInput(data=payload, context={"scope": scope, "has_events": bool(data["events"])})
    form.is_valid(raise_exception=True)
    event_rows = []
    for row in data["events"]:
        form_event = EventInput(
            data={**row, "event": row["event_id"]}, context={"scope": scope, "user": user}
        )
        form_event.is_valid(raise_exception=True)
        if form_event.validated_data["rule"] != row["rule"]:
            raise ValidationError(
                _("Die Terminreihe wurde geändert. Bitte die Zuordnung neu prüfen.")
            )
        event_rows.append(form_event.validated_data)
    validate_todos(
        set(data["todos"]) | set(item.todo_links.values_list("todo_id", flat=True)), user, scope
    )
    docs = set(data["documents"]) | set(item.document_links.values_list("document_id", flat=True))
    if access.documents(scope).filter(pk__in=docs).count() != len(docs):
        raise PermissionDenied()
    event_ids = set(item.event_links.values_list("event_id", flat=True))
    if access.events(user, scope).filter(pk__in=event_ids).count() != len(event_ids):
        raise PermissionDenied()
    photo = item.photos.filter(pk=data["photo"]).first() if data["photo"] else None
    if data["photo"] and photo is None:
        raise ValidationError(_("Das frühere Bild ist nicht mehr vorhanden."))
    for key, value in form.validated_data.items():
        setattr(item, key, value)
    item.deleted_at = timezone.now() if data["deleted"] else None
    item.event_links.all().delete()
    item.todo_links.all().delete()
    item.document_links.all().delete()
    for row in event_rows:
        MaterialEventLink.objects.create(**scope_values(item), **row)
    for todo_id in data["todos"]:
        MaterialTodoLink.objects.create(**scope_values(item), todo_id=todo_id)
    for doc_id in data["documents"]:
        MaterialDocumentLink.objects.create(**scope_values(item), document_id=doc_id)
    item.photos.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
    if photo:
        photo.deleted_at = None
        photo.save(update_fields=["deleted_at"])


def image_content(upload, request=None):
    from core.virenscan import scan_bytes

    if not upload or upload.size > 10 * 1024 * 1024:
        raise ValidationError(_("Bitte ein Bild mit höchstens 10 MB wählen."))
    raw = upload.read()
    scan_bytes(raw, upload.name, request=request)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError()
                if source.width * source.height > 20_000_000:
                    raise ValueError()
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600, 1600))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=85)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError(_("Bitte ein gültiges JPEG-, PNG- oder WebP-Bild wählen.")) from exc
    return ContentFile(output.getvalue(), name="material.jpg")


def delete_photo_files(photos):
    for photo in photos:
        storage, name = photo.file.storage, photo.file.name
        transaction.on_commit(lambda s=storage, n=name: s.delete(n))


def ensure_no_music_loan(item):
    from music.models import EquipmentLoan

    if EquipmentLoan.objects.filter(equipment__item=item, returned_at=None).exists():
        raise ValidationError(_("Bitte die Musikausstattung vor dem Löschen zurücknehmen."))
