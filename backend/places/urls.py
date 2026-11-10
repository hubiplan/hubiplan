from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("suggestions/", views.SuggestionsView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
]
