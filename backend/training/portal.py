"""Training im Mitgliederbereich und in der App (``/api/portal/<Zugang>/training/…``).

Mitglieder sehen ihre Anwesenheit und ihr Schießbuch, checken per QR-Code ein und melden
Schießtermine (der Vorstand bestätigt sie). Wer in der Verwaltung ``training.edit`` hat
(Verein oder Untereinheit), führt die Anwesenheitsliste auch hier, damit das unterwegs aus der
App geht.

- ``training/``: eigene Anwesenheit, offenes Einchecken, Schießbuch mit Stand, Ziele zum Erfassen
- ``training/<id>/checkin/``: einchecken mit dem Code vom Bildschirm
- ``training/shooting/``: Schießtermin melden; ``training/shooting/<id>/``: Meldung zurückziehen
- ``training/manage/``: Termine der Einheiten, in denen man erfassen darf; anlegen
- ``training/manage/<id>/``: Termin mit Liste; ``…/attendance/``; ``…/checkin/``
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from changes import idempotency
from core.tenancy import scope_of, set_rls, user_view

from . import access, services
from .models import ShootingEntry, TrainingSession
from .views import detail_data, membership_in


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        found = _portal_access(user, access_id)
    set_rls(found.organization_id, user.pk, scope_id=scope_of(found.organization_id))
    if access.MODULE not in (found.organization.enabled_modules or []):
        raise NotFound()
    if found.contact_person_id is not None or found.membership_id is None:
        raise NotFound()
    if not found.membership.current_period():
        raise NotFound()
    return found


def targets(user, org) -> list[dict]:
    """Wo dieses Konto die Anwesenheit erfassen darf: Verein und/oder Untereinheiten."""
    from access.permissions import permissions_in
    from portal.services import department_contexts

    out = []
    if access.EDIT in permissions_in(user, org):
        out.append({"department": None, "name": org.name})
    for dept_id, ctx in sorted(
        department_contexts(user).items(), key=lambda kv: kv[1].department.name
    ):
        if ctx.club.pk == org.pk and access.EDIT in ctx.permissions:
            out.append({"department": dept_id, "name": ctx.department.name})
    # department_contexts setzt den Zeilenschutz je Verein; zurück auf diesen Verein
    set_rls(org.pk, user.pk, scope_id=scope_of(org.pk))
    return out


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization
        self.membership = self.access.membership

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def editable_departments(self) -> set:
        return {t["department"] for t in targets(self.request.user, self.org)}


def open_checkins(org) -> list[dict]:
    on = services.today()
    rows = TrainingSession.objects.filter(
        organization=org,
        checkin_open=True,
        date__gte=on - datetime.timedelta(days=services.CHECKIN_DAYS),
        date__lte=on + datetime.timedelta(days=services.CHECKIN_DAYS),
    ).select_related("department")
    return [services.session_data(s, count=0) for s in rows]


def member_view(membership, user) -> dict:
    org = membership.organization
    on = services.today()
    start = services.add_months(on, -24) + datetime.timedelta(days=1)
    attended = services.member_attendance(membership, start, on)
    year_start = datetime.date(on.year, 1, 1)
    data = {
        "attendance": attended,
        "count_year": sum(1 for a in attended if a["date"] >= year_start),
        "count_12": sum(1 for a in attended if a["date"] > services.add_months(on, -12)),
        "checkin": [
            {**s, "present": s["id"] in {a["session"] for a in attended}}
            for s in open_checkins(org)
        ],
        "shooting_enabled": access.shooting_on(org),
        "targets": targets(user, org),
    }
    if data["shooting_enabled"]:
        entries = ShootingEntry.objects.filter(membership=membership).order_by("-date", "-pk")
        data["shooting"] = {
            "entries": [services.entry_data(e) for e in entries[: services.LIST_LIMIT]],
            "evaluation": services.evaluate(membership, on),
            "disciplines": services.disciplines(org),
        }
    return data


class OverviewView(Base):
    def get(self, request, **kwargs):
        return Response(member_view(self.membership, request.user))


class CheckinView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        session = get_object_or_404(
            TrainingSession.objects.select_for_update(of=("self",)).select_related(
                "organization", "department"
            ),
            pk=pk,
            organization=self.org,
        )
        if session.department_id is not None:
            # Einchecken bei einer Untereinheit: nur wer dort Mitglied ist
            if not services.candidates(session).filter(pk=self.membership.pk).exists():
                raise ValidationError(
                    {
                        "detail": _(
                            "Dieses Training gehört zu einer Untereinheit, in der du nicht "
                            "Mitglied bist."
                        )
                    }
                )
        services.check_in(
            session, self.membership, str(request.data.get("code") or ""), request.user
        )
        return Response(member_view(self.membership, request.user))


class ShootingView(Base):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not access.shooting_on(self.org):
            raise NotFound()

    @transaction.atomic
    def post(self, request, **kwargs):
        key = idempotency.claim(request, f"training.shooting.{self.access.pk}")
        if not key.done:
            entry = services.add_entry(
                self.org, self.membership, request.user, request.data, by_member=True
            )
            key.remember({"id": entry.pk})
        return Response(member_view(self.membership, request.user), status=201)


class ShootingEntryView(ShootingView):
    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        entry = get_object_or_404(
            ShootingEntry, pk=pk, organization=self.org, membership=self.membership
        )
        if entry.status != ShootingEntry.Status.REPORTED:
            raise PermissionDenied()
        record(self.org, request.user, "delete", entry, diff(snapshot(entry), {}))
        entry.delete()
        return Response(member_view(self.membership, request.user))


# --- Anwesenheit erfassen (Übungsleitung, Vorstand) -------------------------------------


class ManageBase(Base):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.allowed = self.editable_departments()
        if not self.allowed:
            raise PermissionDenied()

    def sessions(self):
        from django.db.models import Q

        depts = [d for d in self.allowed if d is not None]
        q = Q(department_id__in=depts)
        if None in self.allowed:
            q |= Q(department__isnull=True)
        return TrainingSession.objects.filter(q, organization=self.org)

    def session(self, pk, *, lock=False):
        qs = self.sessions().select_related("department", "organization")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)


class ManageListView(ManageBase):
    def get(self, request, **kwargs):
        from django.db.models import Count

        on = services.today()
        rows = (
            self.sessions()
            .filter(
                date__gte=on - datetime.timedelta(days=60),
                date__lte=on + datetime.timedelta(days=30),
            )
            .select_related("department")
            .annotate(n=Count("attendances"))[:100]
        )
        return Response(
            {
                "sessions": [services.session_data(s, count=s.n) for s in rows],
                "targets": targets(request.user, self.org),
                "kinds": [
                    {"value": v, "label": str(lbl)} for v, lbl in TrainingSession.Kind.choices
                ],
                "shooting_enabled": access.shooting_on(self.org),
                "disciplines": services.disciplines(self.org)
                if access.shooting_on(self.org)
                else [],
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
        if dept_id not in self.allowed:
            raise PermissionDenied()
        key = idempotency.claim(request, f"training.portal.{self.access.pk}")
        if key.done:
            session = self.session(key.result["id"])
            return Response(detail_data(session, can_edit=True))
        department = (
            get_object_or_404(Department, pk=dept_id, organization=self.org) if dept_id else None
        )
        data = dict(request.data.items()) if hasattr(request.data, "items") else {}
        session = services.create_session(self.org, department, request.user, data)
        key.remember({"id": session.pk})
        return Response(detail_data(session, can_edit=True), status=201)


class ManageDetailView(ManageBase):
    def get(self, request, pk, **kwargs):
        return Response(detail_data(self.session(pk), can_edit=True))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        session = services.update_session(self.session(pk, lock=True), request.user, request.data)
        return Response(detail_data(session, can_edit=True))


class ManageAttendanceView(ManageBase):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        session = self.session(pk, lock=True)
        membership = membership_in(session, request.data.get("membership"))
        present = services.as_bool(request.data.get("present", True))
        services.set_present(session, membership, present, request.user)
        return Response(detail_data(session, can_edit=True))


class ManageCheckinView(ManageBase):
    def get(self, request, pk, **kwargs):
        session = self.session(pk)
        if not session.checkin_open:
            raise NotFound()
        data = services.current_code(session)
        data["count"] = session.attendances.count()
        return Response(data)

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        session = self.session(pk, lock=True)
        services.open_checkin(session, services.as_bool(request.data.get("open", True)))
        return Response(detail_data(session, can_edit=True))
