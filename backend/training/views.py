"""Training und Anwesenheit in der Verwaltung (Verein und Untereinheit) sowie das Schießbuch.

Verein oder Untereinheit (``/api/orgs/<id>/training/…``, ``/api/departments/<id>/training/…``):

- ``training/``: Termine (``?von=``, ``?bis=``), anlegen
- ``training/options/``: Arten, Disziplinen, Termine aus dem Kalender als Vorschlag
- ``training/report/``: Teilnahmen je Mitglied (``?von=``, ``?bis=``, ``?format=xlsx``)
- ``training/<id>/``: ansehen (mit Anwesenheitsliste), ändern, löschen
- ``training/<id>/attendance/``: an- oder abhaken (``membership``, ``present``)
- ``training/<id>/checkin/``: Einchecken per QR-Code öffnen/schließen, aktueller Code (GET)

Schießbuch, nur im Verein und mit Modul „Schießsport“ (``/api/orgs/<id>/…``):

- ``shooting-log/``: Mitglieder mit Einträgen, gemeldete Einträge (``?status=reported``)
- ``members/<id>/shooting-log/``: Einträge und Stand nach § 14 WaffG, Eintrag anlegen
- ``members/<id>/shooting-log/pdf/``: Bestätigung der Schießtermine (``?von=``, ``?bis=``,
  ``?waffe=``)
- ``shooting-log/<id>/``: ändern, löschen; ``shooting-log/<id>/confirm/`` bzw. ``reject/``
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from members.models import Membership

from . import access, report, services
from .models import ShootingEntry, TrainingSession


def _date_param(request, key, default):
    raw = request.query_params.get(key)
    if not raw:
        return default
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        raise ValidationError({key: _("Bitte ein gültiges Datum angeben.")}) from None


def period(request, *, back_months=6, ahead_days=60) -> tuple[datetime.date, datetime.date]:
    on = services.today()
    start = _date_param(request, "von", services.add_months(on, -back_months))
    end = _date_param(request, "bis", on + datetime.timedelta(days=ahead_days))
    if end < start:
        raise ValidationError({"bis": _("Das Ende liegt vor dem Beginn.")})
    if (end - start).days > 3 * 366:
        raise ValidationError({"bis": _("Höchstens drei Jahre auf einmal.")})
    return start, end


def file_response(data: bytes, name: str, content_type: str) -> HttpResponse:
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "private, no-store"
    return response


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def event_suggestions(org, department_id, existing: set) -> list[dict]:
    """Einzeltermine aus dem Kalender der Einheit (zwei Wochen zurück und voraus)."""
    if "events" not in (org.enabled_modules or []):
        return []
    from events.models import Event
    from events.recurrence import occurrences

    now = timezone.now()
    events = Event.objects.filter(organization=org, department_id=department_id)
    out = []
    for occ in occurrences(
        events, now - datetime.timedelta(days=14), now + datetime.timedelta(days=14)
    ):
        if occ.is_cancelled:
            continue
        starts = timezone.localtime(occ.starts_at)
        ends = timezone.localtime(occ.ends_at) if occ.ends_at else None
        if (occ.event.pk, starts.date()) in existing:
            continue
        out.append(
            {
                "event": occ.event.pk,
                "date": starts.date(),
                "starts_at": None if occ.event.all_day else starts.strftime("%H:%M"),
                "ends_at": None if occ.event.all_day or ends is None else ends.strftime("%H:%M"),
                "title": occ.event.title,
                "location": occ.event.location,
            }
        )
    return sorted(out, key=lambda r: (r["date"], r["starts_at"] or ""))[:40]


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def sessions(self):
        return TrainingSession.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id
        )

    def session(self, pk, *, lock=False):
        qs = self.sessions().select_related("department", "organization")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def department(self):
        from organizations.models import Department

        if self.scope.department_id is None:
            return None
        return Department.objects.get(pk=self.scope.department_id)

    def event(self, pk):
        from events.models import Event

        if not pk:
            return None
        event = Event.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id, pk=pk
        ).first()
        if event is None:
            raise ValidationError({"event": _("Unbekannter Termin.")})
        return event


def detail_data(session: TrainingSession, *, can_edit: bool) -> dict:
    data = services.session_data(session)
    data["attendance"] = services.attendance_rows(session)
    data["can_edit"] = can_edit
    data["checkin_possible"] = services.checkin_possible(session)
    data["shooting_enabled"] = access.shooting_on(session.organization)
    return data


class ListView(Base):
    def get(self, request, **kwargs):
        from django.db.models import Count

        start, end = period(request)
        rows = (
            self.sessions()
            .filter(date__gte=start, date__lte=end)
            .select_related("department")
            .annotate(n=Count("attendances"))[: services.LIST_LIMIT]
        )
        return Response(
            {
                "sessions": [services.session_data(s, count=s.n) for s in rows],
                "can_edit": self.scope.can_edit,
                "start": start,
                "end": end,
            }
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        data = dict(request.data.items()) if hasattr(request.data, "items") else {}
        data["_event"] = self.event(request.data.get("event"))
        session = services.create_session(self.scope.org, self.department(), request.user, data)
        return Response(detail_data(session, can_edit=True), status=201)


class OptionsView(Base):
    def get(self, request, **kwargs):
        existing = set(
            self.sessions()
            .filter(event__isnull=False, date__gte=services.today() - datetime.timedelta(days=15))
            .values_list("event_id", "date")
        )
        return Response(
            {
                "can_edit": self.scope.can_edit,
                "kinds": [
                    {"value": v, "label": str(lbl)} for v, lbl in TrainingSession.Kind.choices
                ],
                "shooting_enabled": access.shooting_on(self.scope.org),
                "disciplines": services.disciplines(self.scope.org)
                if access.shooting_on(self.scope.org)
                else [],
                "events": event_suggestions(self.scope.org, self.scope.department_id, existing)
                if self.scope.can_edit
                else [],
            }
        )


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(detail_data(self.session(pk), can_edit=self.scope.can_edit))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        session = services.update_session(self.session(pk, lock=True), request.user, request.data)
        return Response(detail_data(session, can_edit=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        session = self.session(pk, lock=True)
        record(self.scope.org, request.user, "delete", session, diff(snapshot(session), {}))
        session.delete()
        return Response(status=204)


def membership_in(session: TrainingSession, raw) -> Membership:
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({"membership": _("Bitte ein Mitglied wählen.")}) from None
    membership = services.candidates(session).filter(pk=pk).select_related("person").first()
    if membership is None:
        raise ValidationError({"membership": _("Dieses Mitglied gehört nicht zu dieser Einheit.")})
    return membership


class AttendanceView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Ein Mitglied an- oder abhaken; mit ``members`` (Liste) mehrere auf einmal anhaken."""
        access.require_edit(self.scope)
        session = self.session(pk, lock=True)
        present = services.as_bool(request.data.get("present", True))
        many = request.data.get("members")
        if isinstance(many, list):
            for raw in many[:1000]:
                services.set_present(session, membership_in(session, raw), present, request.user)
        else:
            membership = membership_in(session, request.data.get("membership"))
            services.set_present(session, membership, present, request.user)
        return Response(detail_data(session, can_edit=True))


class CheckinView(Base):
    def get(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        session = self.session(pk)
        if not session.checkin_open:
            raise NotFound()
        data = services.current_code(session)
        data["count"] = session.attendances.count()
        return Response(data)

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        session = self.session(pk, lock=True)
        services.open_checkin(session, services.as_bool(request.data.get("open", True)))
        return Response(detail_data(session, can_edit=True))


class ReportView(Base):
    def get(self, request, **kwargs):
        start, end = period(request, back_months=12, ahead_days=0)
        data = services.report(self.scope.org, self.scope.department_id, start, end)
        if request.query_params.get("format") == "xlsx":
            name = f"anwesenheit-{start:%Y%m%d}-{end:%Y%m%d}.xlsx"
            return file_response(report.report_xlsx(self.scope.org, data), name, XLSX)
        return Response(data)


# --- Schießbuch -------------------------------------------------------------------------


class ShootingBase(Base):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.scope.department_id is not None or not access.shooting_on(self.scope.org):
            raise NotFound()

    def membership(self, member_pk) -> Membership:
        return get_object_or_404(
            Membership.objects.select_related("person"), pk=member_pk, organization=self.scope.org
        )

    def entry(self, pk) -> ShootingEntry:
        return get_object_or_404(
            ShootingEntry.objects.select_for_update(of=("self",)).select_related("membership"),
            pk=pk,
            organization=self.scope.org,
        )


class ShootingOverviewView(ShootingBase):
    def get(self, request, **kwargs):
        from django.db.models import Count, Max, Q

        on = services.today()
        start24 = services.add_months(on, -24)
        rows = (
            ShootingEntry.objects.filter(organization=self.scope.org, date__gt=start24)
            .values("membership_id")
            .annotate(
                total=Count("pk", filter=Q(status=ShootingEntry.Status.CONFIRMED)),
                pending=Count("pk", filter=Q(status=ShootingEntry.Status.REPORTED)),
                last=Max("date", filter=Q(status=ShootingEntry.Status.CONFIRMED)),
            )
        )
        stats = {r["membership_id"]: r for r in rows}
        members = Membership.objects.filter(
            pk__in=stats, organization=self.scope.org
        ).select_related("person")
        people = sorted(
            (
                {
                    "membership": m.pk,
                    "name": services.person_name(m),
                    "count_24": stats[m.pk]["total"],
                    "pending": stats[m.pk]["pending"],
                    "last": stats[m.pk]["last"],
                }
                for m in members
            ),
            key=lambda r: r["name"].lower(),
        )
        reported = (
            ShootingEntry.objects.filter(
                organization=self.scope.org, status=ShootingEntry.Status.REPORTED
            )
            .select_related("membership__person")
            .order_by("date", "pk")[:200]
        )
        return Response(
            {
                "members": people,
                "reported": [
                    {**services.entry_data(e), "name": services.person_name(e.membership)}
                    for e in reported
                ],
                "can_edit": self.scope.can_edit,
                "disciplines": services.disciplines(self.scope.org),
            }
        )


def member_log(membership) -> dict:
    entries = ShootingEntry.objects.filter(membership=membership).order_by("-date", "-pk")
    return {
        "membership": membership.pk,
        "name": services.person_name(membership),
        "entries": [services.entry_data(e) for e in entries[: services.LIST_LIMIT]],
        "evaluation": services.evaluate(membership),
    }


class MemberShootingView(ShootingBase):
    def get(self, request, member_pk, **kwargs):
        data = member_log(self.membership(member_pk))
        data["can_edit"] = self.scope.can_edit
        data["disciplines"] = services.disciplines(self.scope.org)
        return Response(data)

    @transaction.atomic
    def post(self, request, member_pk, **kwargs):
        access.require_edit(self.scope)
        membership = self.membership(member_pk)
        services.add_entry(self.scope.org, membership, request.user, request.data, by_member=False)
        data = member_log(membership)
        data["can_edit"] = True
        return Response(data, status=201)


class MemberShootingPdfView(ShootingBase):
    def get(self, request, member_pk, **kwargs):
        membership = self.membership(member_pk)
        on = services.today()
        end = _date_param(request, "bis", on)
        start = _date_param(request, "von", services.add_months(end, -24) + datetime.timedelta(1))
        if end < start:
            raise ValidationError({"bis": _("Das Ende liegt vor dem Beginn.")})
        wclass = request.query_params.get("waffe") or ""
        if wclass and wclass not in services.WeaponClass.values:
            raise ValidationError({"waffe": _("Bitte Kurz- oder Langwaffe wählen.")})
        pdf = report.proof_pdf(self.scope.org, membership, start, end, wclass)
        return file_response(
            pdf, f"schiessnachweis-{membership.pk}-{end:%Y%m%d}.pdf", "application/pdf"
        )


class ShootingEntryView(ShootingBase):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        entry = services.update_entry(self.entry(pk), request.user, request.data)
        return Response(services.entry_data(entry))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        entry = self.entry(pk)
        if entry.attendance_id is not None:
            raise ValidationError(
                {"detail": _("Dieser Eintrag kommt aus dem Training. Bitte dort austragen.")}
            )
        record(self.scope.org, request.user, "delete", entry, diff(snapshot(entry), {}))
        entry.delete()
        return Response(status=204)


class ShootingDecideView(ShootingBase):
    @transaction.atomic
    def post(self, request, pk, action, **kwargs):
        access.require_edit(self.scope)
        if action not in ("confirm", "reject"):
            raise NotFound()
        entry = services.decide_entry(self.entry(pk), request.user, action == "confirm")
        return Response(services.entry_data(entry))
