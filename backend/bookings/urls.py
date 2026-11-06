from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("items/", views.ItemsView.as_view()),
    path("choices/", views.ChoicesView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/decision/", views.DecisionView.as_view()),
    path("<int:pk>/skip/", views.SkipView.as_view()),
    path("<int:pk>/handover/", views.HandoverView.as_view()),
]
