"""Anhänge von Terminen: hochgeladene Dateien und verknüpfte Dokumente der Ablage.

Ein verknüpftes Dokument zeigt immer seine neueste Fassung. Wer den Termin sehen
darf, sieht auch das Dokument, selbst wenn dessen Ordner enger sichtbar ist: Die
Verknüpfung ist eine bewusste Freigabe durch jemanden, der den Termin bearbeiten
und das Dokument in der Ablage lesen darf. Liegt das Dokument im Papierkorb oder
ist es gelöscht, ist der Anhang nicht verfügbar; wiederhergestellt gilt er wieder.
Auf die öffentliche Webseite kommen Anhänge nie.
"""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.utils.translation import gettext

from core.tenancy import rls_bypass
from documents.models import DocumentVersion, Folder

from .models import EventAttachment


def linked_version(att: EventAttachment) -> DocumentVersion | None:
    """Neueste Fassung des verknüpften Dokuments, sonst ``None``."""
    if att.kind != EventAttachment.Kind.DOCUMENT or not att.document_id:
        return None
    cached = getattr(att, "_linked_version", False)
    if cached is not False:
        return cached
    # Der Ordner kann enger sichtbar sein als der Termin (siehe oben); die Sicht auf
    # den Termin ist schon geprüft, daher hier ohne RLS.
    with rls_bypass():
        version = (
            DocumentVersion.objects.filter(
                document_id=att.document_id, document__deleted_at__isnull=True
            )
            .select_related("document")
            .order_by("-uploaded_at", "-pk")
            .first()
        )
    att._linked_version = version
    return version


def available(att: EventAttachment) -> bool:
    return att.kind == EventAttachment.Kind.FILE or linked_version(att) is not None


def file_of(att: EventAttachment):
    """Datei, Name, Art und Größe zum Ausliefern, sonst ``None``."""
    if att.kind == EventAttachment.Kind.FILE:
        return att.file, att.name, att.content_type, att.size
    version = linked_version(att)
    if version is None:
        return None
    return version.file, version.name, version.content_type, version.size


def display_name(att: EventAttachment) -> str:
    if att.kind == EventAttachment.Kind.FILE:
        return att.name
    version = linked_version(att)
    if version is None:
        return gettext("Dokument nicht mehr in der Ablage")
    return version.document.title


def data(att: EventAttachment, url: str) -> dict:
    found = file_of(att)
    return {
        "id": att.pk,
        "kind": att.kind,
        "name": display_name(att),
        "file_name": found[1] if found else "",
        "size": found[3] if found else 0,
        "content_type": found[2] if found else "",
        "document": att.document_id if att.kind == EventAttachment.Kind.DOCUMENT else None,
        "available": found is not None,
        "url": url,
    }


def shown(event, can_edit: bool) -> list[EventAttachment]:
    """Anhänge für die Anzeige: Nicht verfügbare Verknüpfungen nur für Bearbeitende."""
    return [a for a in event.attachments.all() if can_edit or available(a)]


def response(request, att: EventAttachment, cache: str) -> FileResponse:
    """Anhang ausliefern; gesperrt, solange die Virenprüfung aussteht."""
    from core import virenscan

    found = file_of(att)
    if found is None:
        raise Http404
    file, name, content_type, _ = found
    with rls_bypass():
        virenscan.ensure_released(file)
        try:
            handle = file.open("rb")
        except FileNotFoundError as exc:
            raise Http404 from exc
    result = FileResponse(
        handle,
        content_type=content_type or "application/octet-stream",
        as_attachment=request.query_params.get("download") == "1",
        filename=name,
    )
    result["Cache-Control"] = cache
    result["X-Content-Type-Options"] = "nosniff"
    return result


def narrower(folder: Folder, event_visibility: str) -> bool:
    """Ist der Ordner enger sichtbar als der Termin? Dann warnt der Dialog."""
    if folder.visibility == Folder.Visibility.PUBLIC:
        return False
    if folder.visibility == Folder.Visibility.BOARD:
        return event_visibility != "board"
    # Mitglieder- oder Vereinsordner: enger nur bei öffentlichen Terminen
    return event_visibility == "public"
