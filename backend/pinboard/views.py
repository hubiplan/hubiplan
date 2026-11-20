"""Pinnwand in der Verwaltung (Verein und Untereinheit): Beiträge anlegen, ändern, löschen."""

from __future__ import annotations

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot

from . import access, services
from .models import Notice


def conflict():
    exc = APIException(_("Der Beitrag wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


def prefix_of(request) -> str:
    return request.path.split("pinboard/")[0] + "pinboard/"


def photo_response(photo):
    response = FileResponse(photo.file.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def create_notice(org, department, user, data, files, request=None) -> Notice:
    """Gemeinsam für Verwaltung und Mitgliederbereich/App. Push nach dem Speichern."""
    fields = services.clean_fields(data)
    notice = Notice.objects.create(
        organization=org,
        department=department,
        created_by=user,
        author=services.author_name(user, org),
        push=services.as_bool(data.get("push")),
        **fields,
    )
    services.add_photos(notice, files.getlist("photos") if files else [], request)
    record(org, user, "create", notice, diff({}, snapshot(notice)))
    if notice.push:
        from .tasks import notify

        transaction.on_commit(lambda: notify.delay(notice.pk))
    return notice


def update_notice(org, user, pk, data) -> Notice:
    """Text, Anheften, „Anzeigen bis“ ändern (mit Versionsprüfung, falls angegeben)."""
    notice = (
        Notice.objects.select_for_update(of=("self",))
        .select_related("department", "organization")
        .get(pk=pk, organization=org)
    )
    version = data.get("version")
    if version is not None and str(version) != str(notice.version):
        raise conflict()
    before = snapshot(notice)
    fields = services.clean_fields(data, partial=True)
    for key, value in fields.items():
        setattr(notice, key, value)
    if "text" in fields:
        notice.edited_at = timezone.now()
    notice.version += 1
    notice.save()
    changes = diff(before, snapshot(notice))
    if changes:
        record(org, user, "update", notice, changes)
    return notice


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))
        self.prefix = prefix_of(request)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def notices(self):
        return Notice.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id
        )

    def notice(self, pk, *, lock=False):
        qs = self.notices().select_related("department", "organization")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def data(self, notice):
        return services.notice_data(notice, self.prefix, can_edit=self.scope.can_edit)

    def department(self):
        from organizations.models import Department

        if self.scope.department_id is None:
            return None
        return Department.objects.get(pk=self.scope.department_id)


class ListView(Base):
    def get(self, request, **kwargs):
        rows = (
            self.notices().select_related("department", "organization").prefetch_related("photos")
        )
        return Response(
            {
                "notices": [self.data(n) for n in rows],
                "can_edit": self.scope.can_edit,
                "max_photos": services.MAX_PHOTOS,
                "max_text": services.MAX_TEXT,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        notice = create_notice(
            self.scope.org, self.department(), request.user, request.data, request.FILES, request
        )
        return Response(self.data(notice), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(self.data(self.notice(pk)))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        notice = self.notice(pk)
        return Response(
            self.data(update_notice(self.scope.org, request.user, notice.pk, request.data))
        )

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        notice = self.notice(pk, lock=True)
        record(self.scope.org, request.user, "delete", notice, diff(snapshot(notice), {}))
        notice.delete()
        return Response(status=204)


class PhotosView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        notice = self.notice(pk, lock=True)
        services.add_photos(notice, request.FILES.getlist("photos"), request)
        Notice.objects.filter(pk=notice.pk).update(version=notice.version + 1)
        notice.refresh_from_db()
        return Response(self.data(notice))


class PhotoView(Base):
    def get(self, request, pk, photo_id, **kwargs):
        photo = get_object_or_404(self.notice(pk).photos, pk=photo_id)
        return photo_response(photo)

    @transaction.atomic
    def delete(self, request, pk, photo_id, **kwargs):
        access.require_edit(self.scope)
        notice = self.notice(pk, lock=True)
        get_object_or_404(notice.photos, pk=photo_id).delete()
        Notice.objects.filter(pk=notice.pk).update(version=notice.version + 1)
        notice.refresh_from_db()
        return Response(self.data(notice))
