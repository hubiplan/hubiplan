"""Beschlussbuch (Schritt V5): alle freigegebenen Beschlüsse und Wahlen einer Einheit.

Suche und Filter laufen in Python, weil Beschlusstexte verschlüsselt gespeichert sind. Ein
Beschluss lässt sich als umgesetzt oder aufgehoben markieren und als Aufgabe anlegen.
"""

from __future__ import annotations

import io

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Font
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from audit.log import record
from exchange.export import safe_cell

from . import access
from .models import Meeting, Resolution
from .views import Base

MAX_ROWS = 2000


def released(scope):
    return (
        Resolution.objects.filter(
            organization=scope.org,
            meeting__department_id=scope.department_id,
            meeting__status=Meeting.Status.DONE,
        )
        .exclude(number="")
        .select_related("meeting__event", "meeting__kind", "agenda_item", "todo")
        .order_by("-meeting__event__starts_at", "agenda_item__position", "position", "pk")
    )


def book_data(r: Resolution) -> dict:
    # Fremde private Aufgaben blendet die Zeilensicherheit aus; dann nur „hat Aufgabe“
    todo = r.todo if r.todo_id else None
    if todo is not None and todo.deleted_at is not None:
        todo = None
    return {
        "id": r.pk,
        "number": r.number,
        "kind": r.kind,
        "text": r.text,
        "result": r.result,
        "votes_yes": r.votes_yes,
        "votes_no": r.votes_no,
        "votes_abstain": r.votes_abstain,
        "unanimous": r.unanimous,
        "office": r.office,
        "elected_name": r.elected_name,
        # Mitgliedschaft der gewählten Person: „Ins Amt übernehmen“ (Rollen besetzen)
        "elected": r.elected_id,
        "status": r.status,
        "meeting": r.meeting_id,
        "meeting_title": r.meeting.event.title,
        "meeting_kind": r.meeting.kind_id,
        "meeting_kind_name": r.meeting.kind.name,
        "date": timezone.localtime(r.meeting.event.starts_at).date(),
        "agenda_title": r.agenda_item.title,
        "agenda_number": r.agenda_item.number,
        "has_todo": todo is not None or (r.todo_id is not None and r.todo is None),
        "todo": {"id": todo.pk, "title": todo.title, "status": todo.status} if todo else None,
    }


def filtered(scope, params) -> list[Resolution]:
    rows = list(released(scope)[:MAX_ROWS])
    year = params.get("jahr")
    if year and year.isdigit():
        rows = [r for r in rows if timezone.localtime(r.meeting.event.starts_at).year == int(year)]
    kind = params.get("art")
    if kind and kind.isdigit():
        rows = [r for r in rows if r.meeting.kind_id == int(kind)]
    typ = params.get("typ")
    if typ in Resolution.Kind.values:
        rows = [r for r in rows if r.kind == typ]
    status = params.get("stand")
    if status in Resolution.Status.values:
        rows = [r for r in rows if r.status == status]
    term = (params.get("suche") or "").strip().casefold()
    if term:
        rows = [
            r
            for r in rows
            if any(
                term in (value or "").casefold()
                for value in (
                    r.number,
                    r.text,
                    r.office,
                    r.elected_name,
                    r.agenda_item.title,
                    r.meeting.event.title,
                )
            )
        ]
    return rows


class BookView(Base):
    def get(self, request, **kwargs):
        rows = filtered(self.scope, request.query_params)
        years = sorted(
            {timezone.localtime(r.meeting.event.starts_at).year for r in released(self.scope)},
            reverse=True,
        )
        return Response(
            {
                "rows": [book_data(r) for r in rows],
                "years": years,
                "can_todo": todo_allowed(request.user, self.scope),
            }
        )


class BookExportView(Base):
    def get(self, request, **kwargs):
        rows = filtered(self.scope, request.query_params)
        wb = Workbook()
        ws = wb.active
        ws.title = _("Beschlussbuch")[:31]
        head = [
            _("Nummer"),
            _("Datum"),
            _("Versammlung"),
            _("Tagesordnungspunkt"),
            _("Art"),
            _("Beschlusstext"),
            _("Ergebnis"),
            _("Ja"),
            _("Nein"),
            _("Enthaltung"),
            _("Amt"),
            _("Gewählt"),
            _("Stand"),
        ]
        ws.append(head)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for r in rows:
            ws.append(
                [
                    safe_cell(v)
                    for v in (
                        r.number,
                        timezone.localtime(r.meeting.event.starts_at).date(),
                        r.meeting.event.title,
                        r.agenda_item.title,
                        r.get_kind_display(),
                        r.text,
                        _("einstimmig") if r.unanimous else r.get_result_display(),
                        r.votes_yes,
                        r.votes_no,
                        r.votes_abstain,
                        r.office,
                        r.elected_name,
                        r.get_status_display(),
                    )
                ]
            )
        out = io.BytesIO()
        wb.save(out)
        response = HttpResponse(
            out.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="beschlussbuch.xlsx"'
        response["Cache-Control"] = "private, no-store"
        return response


class StatusInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=Resolution.Status.choices)


class BookDetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        resolution = get_object_or_404(released(self.scope).select_for_update(of=("self",)), pk=pk)
        ser = StatusInput(data=request.data)
        ser.is_valid(raise_exception=True)
        before = resolution.status
        resolution.status = ser.validated_data["status"]
        resolution.save(update_fields=["status"])
        if before != resolution.status:
            record(
                self.scope.org,
                request.user,
                "update",
                resolution.meeting,
                {
                    _("Beschluss {number}").format(number=resolution.number): [
                        Resolution.Status(before).label,
                        resolution.get_status_display(),
                    ]
                },
            )
        return Response(book_data(resolution))


def todo_allowed(user, scope) -> bool:
    return "todos.edit" in scope.permissions


class TodoInput(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class BookTodoView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        """Beschluss als eigene Aufgabe anlegen (Erledigung nachverfolgen)."""
        from todos import access as todo_access
        from todos.models import Todo

        access.require_edit(self.scope)
        if not todo_allowed(request.user, self.scope):
            raise PermissionDenied()
        resolution = get_object_or_404(released(self.scope).select_for_update(of=("self",)), pk=pk)
        if resolution.todo_id and (resolution.todo is None or resolution.todo.deleted_at is None):
            raise ValidationError({"detail": _("Für diesen Beschluss gibt es schon eine Aufgabe.")})
        ser = TodoInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        # Setzt die Rechte der Aufgaben für diesen Bereich; der Beschluss bleibt sichtbar
        todo_access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))
        title = (data.get("title") or "").strip() or _("Beschluss {number} umsetzen").format(
            number=resolution.number
        )
        meeting = resolution.meeting
        todo = Todo.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            created_by=request.user,
            owner=request.user,
            title=title[:200],
            description=_("Beschluss {number} vom {day} ({meeting}):\n{text}").format(
                number=resolution.number,
                day=timezone.localtime(meeting.event.starts_at).strftime("%d.%m.%Y"),
                meeting=meeting.event.title,
                text=resolution.text,
            ),
            due_date=data.get("due_date"),
        )
        resolution.todo = todo
        resolution.save(update_fields=["todo"])
        record(
            self.scope.org,
            request.user,
            "update",
            meeting,
            {_("Aufgabe zu Beschluss {number}").format(number=resolution.number): [None, title]},
        )
        return Response(book_data(resolution), status=201)
