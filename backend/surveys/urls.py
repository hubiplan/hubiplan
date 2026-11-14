from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("options/", views.OptionsView.as_view()),
    path("members/", views.MembersView.as_view()),
    path("count/", views.CountView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/start/", views.StartView.as_view()),
    path("<int:pk>/close/", views.CloseView.as_view()),
    path("<int:pk>/copy/", views.CopyView.as_view()),
    path("<int:pk>/answers/", views.AnswersView.as_view()),
    path("<int:pk>/event/", views.EventFromDateView.as_view()),
    path("<int:pk>/export/", views.ExportView.as_view()),
]
