from django.urls import path

from . import book, views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("kinds/", views.KindsView.as_view()),
    path("resolutions/", book.BookView.as_view()),
    path("resolutions/export/", book.BookExportView.as_view()),
    path("resolutions/<int:pk>/", book.BookDetailView.as_view()),
    path("resolutions/<int:pk>/todo/", book.BookTodoView.as_view()),
    path("kinds/<int:pk>/", views.KindDetailView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/agenda/", views.AgendaView.as_view()),
    path("<int:pk>/invitation/", views.InvitationView.as_view()),
    path("<int:pk>/minutes/", views.MinutesView.as_view()),
    path("<int:pk>/minutes/confirm/", views.ConfirmView.as_view()),
    path("<int:pk>/minutes/pdf/", views.MinutesPdfView.as_view()),
    path("<int:pk>/attendance/", views.AttendanceView.as_view()),
    path("<int:pk>/attendance/<int:entry>/", views.AttendanceDetailView.as_view()),
]
