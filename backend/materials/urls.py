from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("choices/", views.ChoicesView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/restore/", views.RestoreView.as_view()),
    path("<int:pk>/links/", views.LinksView.as_view()),
    path("<int:pk>/history/", views.HistoryView.as_view()),
    path("<int:pk>/photo/", views.PhotoView.as_view()),
    path("<int:pk>/documents/<int:doc_id>/", views.DocumentView.as_view()),
]
