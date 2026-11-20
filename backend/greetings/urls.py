from django.urls import path

from . import views

urlpatterns = [
    path("", views.OverviewView.as_view()),
    path("settings/", views.SettingsView.as_view()),
    path("<int:pk>/send/", views.SendView.as_view()),
    path("<int:pk>/skip/", views.SkipView.as_view()),
    path("<int:pk>/restore/", views.RestoreView.as_view()),
]
