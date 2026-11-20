from django.urls import path

from . import views

urlpatterns = [
    path("", views.OverviewView.as_view()),
    path("settings/", views.SettingsView.as_view()),
    path("hide/", views.HideView.as_view()),
    path("activities/", views.ActivityListView.as_view()),
    path("activities/<int:pk>/", views.ActivityDetailView.as_view()),
    path("breaches/", views.BreachListView.as_view()),
    path("breaches/<int:pk>/", views.BreachDetailView.as_view()),
]
