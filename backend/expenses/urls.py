"""Pfade der Auslagen: Verein (``org_patterns``), Untereinheit (``dept_patterns``),
Mitgliederbereich (``portal_patterns``) und Link (``public_patterns``)."""

from django.urls import path

from . import link, portal, transfer, views

org_patterns = [
    path("expenses/", views.ListView.as_view()),
    path("expenses/settings/", views.SettingsView.as_view()),
    path("expenses/options/", views.OptionsView.as_view()),
    path("expenses/review/", views.ReviewView.as_view()),
    path("expenses/transfers/", transfer.TransferRunsView.as_view()),
    path("expenses/transfers/<int:pk>/", transfer.TransferActionView.as_view()),
    path("expenses/links/", link.LinksView.as_view()),
    path("expenses/links/<int:pk>/", link.LinkDetailView.as_view()),
    path("expenses/<int:pk>/", views.DetailView.as_view()),
    path("expenses/<int:pk>/files/", views.FilesView.as_view()),
    path("expenses/<int:pk>/files/<int:file_id>/", views.FileView.as_view()),
    path("expenses/<int:pk>/<str:action>/", views.ActionView.as_view()),
]

dept_patterns = [
    path("expenses/", views.DeptListView.as_view()),
    path("expenses/<int:pk>/", views.DeptDetailView.as_view()),
    path("expenses/<int:pk>/files/<int:file_id>/", views.DeptFileView.as_view()),
    path("expenses/<int:pk>/<str:action>/", views.DeptActionView.as_view()),
]

portal_patterns = [
    path("expenses/", portal.ListView.as_view()),
    path("expenses/<int:pk>/", portal.DetailView.as_view()),
    path("expenses/<int:pk>/files/", portal.FilesView.as_view()),
    path("expenses/<int:pk>/files/<int:file_id>/", portal.FileView.as_view()),
    path("expenses/<int:pk>/<str:action>/", portal.ActionView.as_view()),
]

public_patterns = [
    path("public/expense/<str:token>/", link.PublicLinkView.as_view(), name="public-expense"),
]
