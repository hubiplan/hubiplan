"""Pfade von Training und Anwesenheit: Verein/Untereinheit, Schießbuch und Mitgliederbereich."""

from django.urls import path

from . import portal, views

# /api/orgs/<id>/training/… und /api/depts/<id>/training/…
urlpatterns = [
    path("", views.ListView.as_view()),
    path("options/", views.OptionsView.as_view()),
    path("report/", views.ReportView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/attendance/", views.AttendanceView.as_view()),
    path("<int:pk>/checkin/", views.CheckinView.as_view()),
]

# Schießbuch, nur im Verein (/api/orgs/<id>/…)
org_patterns = [
    path("shooting-log/", views.ShootingOverviewView.as_view()),
    path("shooting-log/<int:pk>/", views.ShootingEntryView.as_view()),
    path("shooting-log/<int:pk>/<str:action>/", views.ShootingDecideView.as_view()),
    path("members/<int:member_pk>/shooting-log/", views.MemberShootingView.as_view()),
    path("members/<int:member_pk>/shooting-log/pdf/", views.MemberShootingPdfView.as_view()),
]

# /api/portal/<Zugang>/…
portal_patterns = [
    path("training/", portal.OverviewView.as_view()),
    path("training/<int:pk>/checkin/", portal.CheckinView.as_view()),
    path("training/shooting/", portal.ShootingView.as_view()),
    path("training/shooting/<int:pk>/", portal.ShootingEntryView.as_view()),
    path("training/manage/", portal.ManageListView.as_view()),
    path("training/manage/<int:pk>/", portal.ManageDetailView.as_view()),
    path("training/manage/<int:pk>/attendance/", portal.ManageAttendanceView.as_view()),
    path("training/manage/<int:pk>/checkin/", portal.ManageCheckinView.as_view()),
]
