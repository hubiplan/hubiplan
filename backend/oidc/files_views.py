"""Dateien mit der Nextcloud: „In Nextcloud ablegen“ und „Aus Nextcloud übernehmen“.

``/api/orgs/<id>/nextcloud-dateien/``: GET Stand (ob und wohin abgelegt werden kann), POST eine
Datei ablegen. ``…/quelle/?pfad=`` listet den Ordner zum Übernehmen, ``…/quelle/datei/?pfad=``
liefert eine Datei daraus an den Browser, der sie wie eine eigene Datei hochlädt.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.utils.translation import gettext
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    CIRCULARS_SEND,
    DOCS_MANAGE,
    EVENTS_MANAGE,
    FINANCE_EDIT,
    FINANCE_VIEW,
    PHOTOS_EDIT,
    ROLES_MANAGE,
    WEBSITE_CONTENT,
    WEBSITE_MANAGE,
)
from core.api_base import OrgScopedMixin
from core.tenancy import rls_bypass

from . import nc_files
from .models import Client, FileItem

# Wer ablegen darf, je Ziel (eines davon genügt)
STORE_PERMS = {
    FileItem.Target.BOARD: (DOCS_MANAGE, FINANCE_VIEW, ROLES_MANAGE),
    FileItem.Target.FINANCE: (FINANCE_VIEW,),
    FileItem.Target.MEMBERS: (DOCS_MANAGE,),
}
# Wer übernehmen darf: wer irgendwo hochladen darf
PICK_PERMS = (
    DOCS_MANAGE,
    FINANCE_EDIT,
    WEBSITE_CONTENT,
    WEBSITE_MANAGE,
    EVENTS_MANAGE,
    CIRCULARS_SEND,
    PHOTOS_EDIT,
)


def _client(org, *, source: bool = False) -> Client | None:
    with rls_bypass():
        qs = Client.objects.filter(organization=org, is_active=True).select_related("organization")
        qs = qs.exclude(files_source="") if source else qs.filter(files_enabled=True)
        return qs.exclude(service_password="").order_by("pk").first()


class FilesView(OrgScopedMixin, APIView):
    read_permission = None
    write_permission = None
    allowed_org_types = ("club", "federation")
    parser_classes = [MultiPartParser]

    def get(self, request, org_id):
        client = _client(self.org)
        source = _client(self.org, source=True)
        perms = self.org_permissions
        targets = []
        if client is not None:
            for target, label in FileItem.Target.choices:
                if perms & set(STORE_PERMS[target]):
                    targets.append(
                        {
                            "key": target,
                            "label": label,
                            "folder": "/".join(
                                [
                                    *nc_files.clean_segments(client.files_root),
                                    nc_files.FOLDERS[target],
                                ]
                            ),
                            "group": nc_files.group_for(client, target),
                        }
                    )
        categories = []
        if client is not None:
            for key, label in FileItem.Category.choices:
                years = nc_files.retention_years(client, key)
                categories.append({"key": key, "label": label, "years": years})
        return Response(
            {
                "store": bool(targets),
                "name": client.name if client else "",
                "targets": targets,
                "categories": categories,
                "pick": source is not None and bool(perms & set(PICK_PERMS)),
            }
        )

    def post(self, request, org_id):
        client = _client(self.org)
        if client is None:
            raise ValidationError({"detail": gettext("„In Nextcloud ablegen“ ist aus.")})
        target = str(request.data.get("target") or "")
        if target not in STORE_PERMS:
            raise ValidationError({"target": gettext("Unbekanntes Ziel.")})
        if not self.org_permissions & set(STORE_PERMS[target]):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": gettext("Bitte eine Datei wählen.")})
        if upload.size > nc_files.MAX_FILE:
            raise ValidationError({"file": gettext("Die Datei ist zu groß (höchstens 50 MB).")})
        from core import virenscan

        # Die Datei geht ohne spätere Prüfung an Nextcloud weiter: zu groß für die
        # Virenprüfung heißt hier ungeprüft
        if virenscan.enabled() and virenscan.required() and upload.size > virenscan.max_bytes():
            raise ValidationError(
                {
                    "file": gettext(
                        "Die Datei ist zu groß für die Virenprüfung (höchstens {mb} MB)."
                    ).format(mb=virenscan.max_bytes() // (1024 * 1024))
                }
            )
        category = str(request.data.get("category") or "")
        if category == FileItem.Category.PERSONAL and request.data.get("personal") not in (
            "1",
            "true",
            True,
        ):
            raise ValidationError(
                {"personal": gettext("Bitte bestätigen, dass die Datei Personendaten enthält.")}
            )
        name = str(request.data.get("filename") or upload.name or "")
        try:
            item = nc_files.store(client, request.user, target, category, name, upload.read())
        except nc_files.FilesError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            {
                "path": item.path,
                "delete_after": item.delete_after.isoformat() if item.delete_after else None,
            },
            status=201,
        )


class _PickBase(OrgScopedMixin, APIView):
    read_permission = PICK_PERMS
    allowed_org_types = ("club", "federation")

    def client(self) -> Client:
        client = _client(self.org, source=True)
        if client is None:
            raise ValidationError(
                {"detail": gettext("Es ist kein Ordner zum Übernehmen eingetragen.")}
            )
        return client


class SourceListView(_PickBase):
    def get(self, request, org_id):
        client = self.client()
        try:
            entries = nc_files.list_source(client, str(request.query_params.get("pfad") or ""))
        except nc_files.FilesError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response([e.__dict__ for e in entries])


class SourceFileView(_PickBase):
    def get(self, request, org_id):
        client = self.client()
        try:
            name, content = nc_files.fetch_source(
                client, str(request.query_params.get("pfad") or "")
            )
        except nc_files.FilesError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        resp = HttpResponse(content, content_type="application/octet-stream")
        resp["Content-Disposition"] = "attachment; filename*=UTF-8''" + _rfc5987(name)
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "no-store"
        return resp


def _rfc5987(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")
