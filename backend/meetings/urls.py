from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("kinds/", views.KindsView.as_view()),
    path("kinds/<int:pk>/", views.KindDetailView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/agenda/", views.AgendaView.as_view()),
]
