import csv
import datetime
import io

from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import access, services
from .models import (
    MaterialDocumentLink,
    MaterialEventLink,
    MaterialItem,
    MaterialPhoto,
    MaterialTodoLink,
)
from .serializers import EventInput, ItemInput, effective_links, item_data


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(
            request.user,
            kwargs.get("org_id"),
            kwargs.get("dept_id"),
            write=request.method not in ("GET", "HEAD", "OPTIONS"),
        )

    def item(self, pk, *, lock=False, trash=False):
        qs = access.items(self.scope, trash=trash)
        if lock:
            qs = qs.select_for_update()
        return get_object_or_404(qs, pk=pk)

    def data(self, item):
        return item_data(item, self.request.user, self.scope, detail=True)


class ListView(Base):
    def get(self, request, **kwargs):
        qs = access.items(self.scope, trash=request.query_params.get("trash") == "1")
        archived = request.query_params.get("archived") == "1"
        if (
            not archived
            and request.query_params.get("trash") != "1"
            and request.query_params.get("condition") != "retired"
        ):
            qs = qs.exclude(condition="retired")
        for key, targets, field in [
            ("member", lambda: access.members(self.scope), "member_id"),
            (
                "todo",
                lambda: access.todos(request.user, self.scope),
                "todo_links__todo_id",
            ),
            (
                "document",
                lambda: access.documents(self.scope),
                "document_links__document_id",
            ),
            (
                "event",
                lambda: access.events(request.user, self.scope),
                "event_links__event_id",
            ),
        ]:
            value = request.query_params.get(key)
            if value:
                if not value.isdecimal():
                    raise ValidationError(_("Ungültige Auswahl."))
                target = get_object_or_404(targets(), pk=int(value))
                qs = qs.filter(**{field: target.pk})
        if condition := request.query_params.get("condition"):
            qs = qs.filter(condition=condition)
        query = request.query_params.get("q", "").casefold().strip()
        rows = []
        for item in qs.distinct().iterator():
            if (
                query
                and query
                not in " ".join(
                    [
                        item.inventory_number,
                        item.title,
                        item.description,
                        item.purpose,
                        *item.address.values(),
                    ]
                ).casefold()
            ):
                continue
            if request.query_params.get("review") == "1" and not (
                item_data(item, request.user, self.scope)["location_review"]
                or self.data(item)["usage_review"]
                or any(r["needs_review"] for r in self.data(item)["events"])
            ):
                continue
            if original := request.query_params.get("original_start"):
                field = serializers.DateTimeField()
                begins = field.run_validation(original)
                # Ein verschobenes Vorkommen wird anhand seiner ursprünglichen Kennung gesucht.
                from events.models import EventException

                exc = EventException.objects.filter(
                    event_id=request.query_params.get("event"), original_start=begins
                ).first()
                actual = exc.starts_at if exc and exc.starts_at else begins
                uses = effective_links(
                    item,
                    request.user,
                    self.scope,
                    start=actual - datetime.timedelta(days=1),
                    end=actual + datetime.timedelta(days=2),
                )
                if not any(
                    u["original_start"] == begins
                    and str(u["event"]) == request.query_params.get("event")
                    for u in uses
                ):
                    continue
            rows.append(item)
        if request.query_params.get("export") == "1":
            if not {"export.lists", "export.full"} & self.scope.permissions:
                raise PermissionDenied()
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            writer.writerow(
                [
                    _("Inventarnummer"),
                    _("Bezeichnung"),
                    _("Kurzbeschreibung"),
                    _("Standort"),
                    _("Verwendungszweck"),
                ]
            )
            for item in rows:
                row = item_data(item, request.user, self.scope)
                values = [
                    row["inventory_number"],
                    row["title"],
                    row["description"],
                    row["member_name"] or ", ".join(row["address"].values()),
                    row["purpose"],
                ]
                writer.writerow(
                    ["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in values]
                )
            response = HttpResponse(
                "\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8"
            )
            response["Content-Disposition"] = 'attachment; filename="material.csv"'
            return response
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError as exc:
            raise ValidationError(_("Ungültige Seite.")) from exc
        page_rows = []
        for item in rows[(page - 1) * 50 : page * 50]:
            row = item_data(item, request.user, self.scope)
            uses = effective_links(item, request.user, self.scope)
            row["next_use"] = uses[0] if uses else None
            page_rows.append(row)
        return Response(
            {
                "items": page_rows,
                "count": len(rows),
                "page": page,
                "can_edit": "material.edit" in self.scope.permissions,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        event_forms = EventInput(
            data=request.data.get("events", []),
            many=True,
            context={"scope": self.scope, "user": request.user},
        )
        event_forms.is_valid(raise_exception=True)
        if any(r["kind"] == "exclude" for r in event_forms.validated_data):
            raise ValidationError(_("Bitte zuerst die Terminreihe zuordnen."))
        form = ItemInput(
            data=request.data,
            context={
                "scope": self.scope,
                "has_events": bool(event_forms.validated_data),
            },
        )
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        values.pop("version", None)
        item = MaterialItem.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            **values,
        )
        for row in event_forms.validated_data:
            MaterialEventLink.objects.get_or_create(
                **services.scope_values(item),
                event=row["event"],
                kind=row["kind"],
                original_start=row.get("original_start"),
                defaults=row,
            )
        services.changed(item, request.user, {}, "create")
        return Response(self.data(item), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(self.data(self.item(pk, trash=request.query_params.get("trash") == "1")))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        item = self.item(pk, lock=True)
        services.expected(item, request.data.get("version"))
        before = services.snapshot(item)
        form = ItemInput(
            data=request.data, partial=True, context={"scope": self.scope, "item": item}
        )
        form.is_valid(raise_exception=True)
        for key, value in form.validated_data.items():
            if key != "version":
                setattr(item, key, value)
        services.changed(item, request.user, before, "update")
        return Response(self.data(item))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        item = self.item(pk, lock=True)
        services.expected(item, request.data.get("version"))
        services.ensure_no_music_loan(item)
        before = services.snapshot(item)
        item.deleted_at = timezone.now()
        services.changed(item, request.user, before, "delete")
        return Response(status=204)


class RestoreView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        item = self.item(pk, lock=True, trash=True)
        services.expected(item, request.data.get("version"))
        before = services.snapshot(item)
        item.deleted_at = None
        services.changed(item, request.user, before, "restore")
        return Response(self.data(item))


class ChoicesView(Base):
    def get(self, request, **kwargs):
        from todos.access import can_edit

        query = request.query_params.get("q", "").casefold().strip()
        kind = request.query_params.get("kind", "member")
        rows = []
        if kind == "member":
            rows = [{"id": r.pk, "title": str(r.person)} for r in access.members(self.scope)]
        elif kind == "event":
            rows = [
                {
                    "id": r.pk,
                    "title": r.title,
                    "series": r.is_series,
                    "starts_at": r.starts_at,
                }
                for r in access.events(request.user, self.scope)
            ]
        elif kind == "todo":
            rows = [
                {"id": r.pk, "title": r.title}
                for r in access.todos(request.user, self.scope)
                if can_edit(r, request.user, self.scope)
            ]
        elif kind == "document":
            rows = [{"id": r.pk, "title": r.title} for r in access.documents(self.scope)]
        else:
            raise ValidationError(_("Ungültige Auswahl."))
        rows = [r for r in rows if query in r["title"].casefold()]
        return Response({"items": rows[:100], "more": len(rows) > 100})


class LinksView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        item = self.item(pk, lock=True)
        services.expected(item, request.data.get("version"))
        before = services.snapshot(item)
        remove = request.data.get("remove") is True
        if item.condition == "retired" and not remove:
            raise ValidationError(_("Ausgesondertes Material kann nicht neu zugeordnet werden."))
        kind = request.data.get("type")
        if kind == "event":
            if remove:
                link = get_object_or_404(
                    item.event_links,
                    pk=request.data.get("id"),
                    event__in=access.events(request.user, self.scope),
                )
                if link.kind == "series":
                    item.event_links.filter(event=link.event, kind="exclude").delete()
                link.delete()
                if not item.purpose and not item.event_links.exclude(kind="exclude").exists():
                    raise ValidationError(_("Bitte zuerst einen Verwendungszweck angeben."))
            else:
                form = EventInput(
                    data=request.data,
                    context={"scope": self.scope, "user": request.user},
                )
                form.is_valid(raise_exception=True)
                row = form.validated_data
                if (
                    row["kind"] == "exclude"
                    and not item.event_links.filter(event=row["event"], kind="series").exists()
                ):
                    raise ValidationError(_("Bitte zuerst die Terminreihe zuordnen."))
                if row["kind"] in ("exclude", "occurrence"):
                    item.event_links.filter(
                        event=row["event"],
                        original_start=row["original_start"],
                        kind__in=["exclude", "occurrence"],
                    ).delete()
                MaterialEventLink.objects.update_or_create(
                    **services.scope_values(item),
                    event=row["event"],
                    kind=row["kind"],
                    original_start=row.get("original_start"),
                    defaults=row,
                )
        elif kind in ("todo", "document"):
            target_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("id"))
            if kind == "todo":
                services.validate_todos([target_id], request.user, self.scope)
                model, field = MaterialTodoLink, "todo_id"
            else:
                get_object_or_404(access.documents(self.scope), pk=target_id)
                model, field = MaterialDocumentLink, "document_id"
            args = {**services.scope_values(item), field: target_id}
            if remove:
                model.objects.filter(**args).delete()
            else:
                model.objects.get_or_create(**args)
        else:
            raise ValidationError(_("Ungültige Auswahl."))
        services.changed(item, request.user, before, "links")
        return Response(self.data(item))


class HistoryView(Base):
    def get(self, request, pk, **kwargs):
        item = self.item(pk, trash=request.query_params.get("trash") == "1")
        revisions = list(item.revisions.select_related("actor")[:50])
        return Response(
            [
                {
                    "id": r.pk,
                    "at": r.created_at,
                    "action": r.action,
                    "actor": str(r.actor) if r.actor else "",
                    "can_undo": not r.action.startswith("music_")
                    and r == revisions[0]
                    and bool(r.data)
                    and r.actor_id == request.user.pk,
                }
                for r in revisions
                if services.revision_visible(r, request.user, self.scope)
            ]
        )

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        item = self.item(pk, lock=True, trash=request.query_params.get("trash") == "1")
        services.expected(item, request.data.get("version"))
        revision = item.revisions.first()
        if (
            not revision
            or revision.action.startswith("music_")
            or revision.pk != request.data.get("revision")
            or revision.actor_id != request.user.pk
            or not revision.data
        ):
            raise ValidationError(_("Nur die letzte eigene Änderung kann zurückgenommen werden."))
        before = services.snapshot(item)
        services.restore_snapshot(item, revision.data, request.user, self.scope)
        services.changed(item, request.user, before, "undo")
        return Response(self.data(item))


class PhotoView(Base):
    def get(self, request, pk, **kwargs):
        photo = get_object_or_404(self.item(pk).photos, deleted_at__isnull=True)
        response = FileResponse(photo.file.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        content = services.image_content(request.FILES.get("file"), request)
        from django.core.exceptions import ValidationError as DjangoValidationError

        from documents.services import check_budget

        try:
            check_budget(self.scope.org, content.size)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        item = self.item(pk, lock=True)
        version = serializers.IntegerField().run_validation(request.data.get("version"))
        services.expected(item, version)
        before = services.snapshot(item)
        item.photos.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
        photo = MaterialPhoto(**services.scope_values(item), size=content.size)
        try:
            photo.file.save("material.jpg", content, save=False)
            photo.save()
            services.changed(item, request.user, before, "photo")
        except Exception:
            if photo.file:
                photo.file.storage.delete(photo.file.name)
            raise
        return Response(self.data(item))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        item = self.item(pk, lock=True)
        services.expected(item, request.data.get("version"))
        before = services.snapshot(item)
        item.photos.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
        services.changed(item, request.user, before, "photo")
        return Response(self.data(item))


class DocumentView(Base):
    def get(self, request, pk, doc_id, **kwargs):
        from documents.views import file_response

        item = self.item(pk)
        link = get_object_or_404(
            item.document_links,
            document_id=doc_id,
            document__in=access.documents(self.scope),
        )
        version = link.document.versions.order_by("-uploaded_at", "-pk").first()
        if not version:
            raise NotFound()
        return file_response(request, version)
