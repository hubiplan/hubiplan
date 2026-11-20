"""Pinnwand im Mitgliederbereich und in der App (/api/portal/<Zugang>/pinboard/…).

Mitglieder lesen. Wer in der Verwaltung ``pinboard.edit`` hat (Verein oder Untereinheit),
schreibt auch hier, damit das unterwegs aus der App geht.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from changes import idempotency
from core.tenancy import scope_of, set_rls, user_view

from . import access as pin_access
from . import services
from .models import Notice
from .views import create_notice, photo_response, prefix_of, update_notice


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if pin_access.MODULE not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership.current_period():
        raise NotFound()
    return access


def targets(user, org) -> list[dict]:
    """Wohin dieses Konto schreiben darf: Verein und/oder Untereinheiten."""
    from access.permissions import permissions_in
    from portal.services import department_contexts

    out = []
    if pin_access.EDIT in permissions_in(user, org):
        out.append({"department": None, "name": org.name})
    for dept_id, ctx in sorted(
        department_contexts(user).items(), key=lambda kv: kv[1].department.name
    ):
        if ctx.club.pk == org.pk and pin_access.EDIT in ctx.permissions:
            out.append({"department": dept_id, "name": ctx.department.name})
    # department_contexts setzt den Zeilenschutz je Verein; zurück auf diesen Verein
    set_rls(org.pk, user.pk, scope_id=scope_of(org.pk))
    return out


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization
        self.prefix = prefix_of(request)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def visible(self):
        return services.visible_for(self.org, self.access.membership_id)

    def editable_departments(self) -> set:
        return {t["department"] for t in targets(self.request.user, self.org)}


class ListView(Base):
    def get(self, request, **kwargs):
        allowed = self.editable_departments()
        rows = list(self.visible()[: services.MEMBER_LIMIT])
        since = services.seen_at(self.access.membership_id)
        data = []
        for n in rows:
            row = services.notice_data(n, self.prefix, can_edit=n.department_id in allowed)
            row["new"] = since is None or n.created_at > since
            data.append(row)
        if request.query_params.get("seen") != "0":
            services.mark_seen(self.org, self.access.membership_id)
        return Response(
            {
                "notices": data,
                "targets": targets(request.user, self.org),
                "max_photos": services.MAX_PHOTOS,
                "max_text": services.MAX_TEXT,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        from organizations.models import Department

        raw = request.data.get("department") or None
        try:
            dept_id = int(raw) if raw not in (None, "", "null") else None
        except (TypeError, ValueError) as exc:
            raise ValidationError({"department": "?"}) from exc
        if dept_id not in self.editable_departments():
            raise PermissionDenied()
        # Aus der App: nach einem Verbindungsabbruch erneut gesendet, entsteht nichts doppelt
        key = idempotency.claim(request, f"pinboard.portal.{self.access.pk}")
        if key.done:
            notice = get_object_or_404(Notice, pk=key.result["id"], organization=self.org)
            return Response(services.notice_data(notice, self.prefix, can_edit=True))
        department = (
            get_object_or_404(Department, pk=dept_id, organization=self.org) if dept_id else None
        )
        notice = create_notice(self.org, department, request.user, request.data, request.FILES)
        key.remember({"id": notice.pk})
        return Response(services.notice_data(notice, self.prefix, can_edit=True), status=201)


class DetailView(Base):
    def notice(self, pk):
        return get_object_or_404(self.visible(), pk=pk)

    def get(self, request, pk, **kwargs):
        notice = self.notice(pk)
        allowed = notice.department_id in self.editable_departments()
        return Response(services.notice_data(notice, self.prefix, can_edit=allowed))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        notice = self.notice(pk)
        if notice.department_id not in self.editable_departments():
            raise PermissionDenied()
        notice = update_notice(self.org, request.user, notice.pk, request.data)
        return Response(services.notice_data(notice, self.prefix, can_edit=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        notice = self.notice(pk)
        if notice.department_id not in self.editable_departments():
            raise PermissionDenied()
        record(self.org, request.user, "delete", notice, diff(snapshot(notice), {}))
        Notice.objects.filter(pk=notice.pk).delete()
        return Response(status=204)


class PhotoView(Base):
    def get(self, request, pk, photo_id, **kwargs):
        notice = get_object_or_404(self.visible(), pk=pk)
        return photo_response(get_object_or_404(notice.photos, pk=photo_id))
