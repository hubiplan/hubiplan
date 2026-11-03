"""Dateien folgen der Aufgabe, Verweise zusätzlich der Dokumentenberechtigung."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from changes.tracking import active
from documents.models import Document
from documents.services import Viewer, check_budget, check_upload, clean_name, storage_name

from .access import can_edit, visible
from .models import TodoAttachment
from .sharing import log_change
from .views import TodoScopeMixin


def documents_for(scope):
    if scope is None or "docs.view" not in scope.permissions:
        return Document.objects.none()
    viewer = Viewer(org=scope.org)
    if scope.department_id:
        from organizations.models import Department

        viewer.kind = "department"
        viewer.department = Department.objects.get(pk=scope.department_id)
    return Document.objects.filter(
        folder__in=viewer.all_folders(), deleted_at__isnull=True
    ).order_by("title", "pk")


def document_for(attachment, scope):
    if attachment.kind != "document" or not attachment.document_id:
        return None
    return documents_for(scope).filter(pk=attachment.document_id).first()


def data_for(attachment, scope):
    doc = document_for(attachment, scope)
    allowed = attachment.kind == "file" or doc is not None
    return {
        "id": attachment.pk,
        "kind": attachment.kind,
        "name": attachment.name
        if attachment.kind == "file"
        else (doc.title if doc else gettext("Dokument ohne Zugriff")),
        "size": attachment.size if attachment.kind == "file" else None,
        "content_type": attachment.content_type if attachment.kind == "file" else None,
        "document": doc.pk if doc else None,
        "available": allowed,
        "uploaded_at": attachment.uploaded_at,
        "deleted_at": attachment.deleted_at,
    }


class AttachmentInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    document = serializers.IntegerField(min_value=1, required=False)
    deleted = serializers.BooleanField(required=False)


class Conflict(APIException):
    status_code = 409


class AttachmentScope(TodoScopeMixin):
    def task(self, request, pk, *, write=False):
        qs = visible(request.user, self.scope)
        todo = get_object_or_404(qs.select_for_update() if write else qs, pk=pk)
        if write and not can_edit(todo, request.user, self.scope):
            raise PermissionDenied()
        return todo

    def input(self, request, todo):
        data = AttachmentInput(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["version"] != todo.version:
            raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
        return data.validated_data

    def changed(self, todo, user):
        ctx = active()
        if ctx:
            ctx.block(gettext("Anhänge werden im Anhang-Papierkorb wiederhergestellt."))
        todo.version += 1
        todo.save(update_fields=["version", "updated_at"])
        log_change(todo, user, "update")


class AttachmentListView(AttachmentScope, APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, pk, **kwargs):
        todo = self.task(request, pk)
        return Response(
            {
                "version": todo.version,
                "items": [data_for(a, self.scope) for a in todo.attachments.order_by("pk")],
                "documents": [{"id": d.pk, "title": d.title} for d in documents_for(self.scope)],
            }
        )

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        todo = self.task(request, pk, write=True)
        values = self.input(request, todo)
        upload = request.FILES.get("file")
        if (upload is not None) == ("document" in values):
            raise serializers.ValidationError(gettext("Bitte eine Datei oder ein Dokument wählen."))
        attachment = TodoAttachment(
            organization=todo.organization,
            department=todo.department,
            todo=todo,
            uploaded_by=request.user,
        )
        if upload is not None:
            try:
                attachment.content_type = check_upload(upload)
                check_budget(todo.organization, upload.size)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict) from exc
            attachment.kind = "file"
            attachment.name = clean_name(upload.name)
            attachment.size = upload.size
            attachment.file.save(storage_name(upload.name), upload, save=False)
        else:
            attachment.kind = "document"
            attachment.document = get_object_or_404(
                documents_for(self.scope), pk=values["document"]
            )
        try:
            attachment.save()
            self.changed(todo, request.user)
        except Exception:
            if attachment.file:
                attachment.file.storage.delete(attachment.file.name)
            raise
        return Response(
            {"attachment": data_for(attachment, self.scope), "version": todo.version}, status=201
        )


class AttachmentDetailView(AttachmentScope, APIView):
    def get(self, request, pk, att_id, **kwargs):
        todo = self.task(request, pk)
        attachment = get_object_or_404(todo.attachments, pk=att_id, deleted_at__isnull=True)
        if attachment.kind == "document":
            doc = document_for(attachment, self.scope)
            version = doc.versions.first() if doc else None
            if version is None:
                raise NotFound()
            from documents.views import file_response

            response = file_response(request, version)
        else:
            response = FileResponse(
                attachment.file.open("rb"),
                filename=attachment.name,
                content_type=attachment.content_type,
                as_attachment=True,
            )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @transaction.atomic
    def patch(self, request, pk, att_id, **kwargs):
        todo = self.task(request, pk, write=True)
        values = self.input(request, todo)
        if "deleted" not in values:
            raise serializers.ValidationError(gettext("Bitte den Papierkorbstatus angeben."))
        attachment = get_object_or_404(todo.attachments, pk=att_id)
        attachment.deleted_at = timezone.now() if values["deleted"] else None
        attachment.save(update_fields=["deleted_at"])
        self.changed(todo, request.user)
        return Response({"attachment": data_for(attachment, self.scope), "version": todo.version})
