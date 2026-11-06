from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("members/", views.MembersView.as_view()),
    path("events/", views.EventsView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/duties/", views.DutiesView.as_view()),
    path("<int:pk>/export/", views.ExportView.as_view()),
    path("duties/<int:pk>/", views.DutyDetailView.as_view()),
    path("duties/<int:pk>/shifts/", views.ShiftsView.as_view()),
    path("shifts/<int:pk>/", views.ShiftDetailView.as_view()),
    path("shifts/<int:pk>/assignments/", views.AssignmentsView.as_view()),
    path("assignments/<int:pk>/", views.AssignmentDetailView.as_view()),
]
