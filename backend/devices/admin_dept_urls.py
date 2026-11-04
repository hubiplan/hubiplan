"""Verwaltung in der App für Untereinheiten (Schritt B4): ``/api/app/v1/admin/d/<Untereinheit>/``.

Für Rollen nur in einer Untereinheit (z. B. Zugführung). Dieselben Ansichten wie im Browser
unter ``/api/depts/<Untereinheit>/…`` mit denselben Rechten (``dept.*``), nur mit dem
Vorstandsschlüssel. Antworten sind damit Teil der App-Schnittstelle (nur abwärtskompatibel
ändern).
"""

from django.urls import path

from changes import views as change_views
from events import views as event_views
from portal import views as portal_views
from todos import attachments as todo_attachments
from todos import cross_views as todo_cross_views
from todos import reminder_views as todo_reminder_views
from todos import series_views as todo_series_views
from todos import views as todo_views

from .admin_api import for_app


def _p(route: str, view, name: str, read_only: bool = False):
    return path(route, for_app(view, read_only).as_view(), name=f"app-admin-dept-{name}")


urlpatterns = [
    path("todos/<int:pk>/progress/", for_app(todo_cross_views.ProgressView).as_view()),
    path(
        "todos/<int:pk>/changes/<uuid:set_id>/undo/",
        for_app(todo_cross_views.TaskUndoView).as_view(),
    ),
    path("todos/<int:pk>/attachments/", for_app(todo_attachments.AttachmentListView).as_view()),
    path(
        "todos/<int:pk>/attachments/<int:att_id>/",
        for_app(todo_attachments.AttachmentDetailView).as_view(),
    ),
    path("todos/<int:pk>/series/", for_app(todo_series_views.SeriesView).as_view()),
    path("todos/<int:pk>/reminders/", for_app(todo_reminder_views.ReminderSettingsView).as_view()),
    path("todos/orphans/", for_app(todo_views.OrphanTasksView).as_view()),
    path("todos/<int:pk>/take-over/", for_app(todo_views.TakeOverView).as_view()),
    path("todos/choices/", for_app(todo_views.TodoChoicesView).as_view()),
    path("todos/", for_app(todo_views.TodoListView).as_view()),
    path("todos/<int:pk>/", for_app(todo_views.TodoDetailView).as_view()),
    _p("", portal_views.DepartmentInfoView, "info", read_only=True),
    _p("members/", portal_views.DepartmentMemberListView, "members"),
    _p("members/<int:pk>/", portal_views.DepartmentMemberDetailView, "member"),
    _p("changes/<uuid:set_id>/undo/", change_views.DeptUndoView, "undo"),
    _p("events/", event_views.DeptEventListView, "events"),
    _p("events/<int:pk>/", event_views.DeptEventDetailView, "event"),
    _p("events/<int:pk>/notify/", event_views.DeptEventNotifyView, "event-notify"),
    _p("events/<int:pk>/occurrence/", event_views.DeptEventOccurrenceView, "event-occurrence"),
    _p("events/<int:pk>/responses/", event_views.DeptResponsesView, "event-responses"),
    _p(
        "events/<int:pk>/responses/<int:membership_id>/",
        event_views.DeptResponseDetailView,
        "event-response",
    ),
]
