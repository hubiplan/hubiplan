"""Adressen der API für andere Programme (docs/api.md)."""

from django.urls import path

from . import manage_views, openapi, views

V1 = "partner/v1/"

# Der Vertrag mit Dritten: /api/partner/v1/…
v1_patterns = [
    path(V1, views.InfoView.as_view(), name="partner-info"),
    path(f"{V1}unit/", views.UnitView.as_view(), name="partner-unit"),
    path(f"{V1}unit/logo", views.UnitLogoView.as_view(), name="partner-unit-logo"),
    path(f"{V1}units/", views.SubUnitsView.as_view(), name="partner-units"),
    path(f"{V1}events/", views.EventsView.as_view(), name="partner-events"),
    path(f"{V1}statistics/census/", views.CensusView.as_view(), name="partner-census"),
    path(f"{V1}board/", views.BoardView.as_view(), name="partner-board"),
    path(f"{V1}results/", views.ResultsView.as_view(), name="partner-results"),
    path(
        f"{V1}results/<str:competition_id>/",
        views.ResultDetailView.as_view(),
        name="partner-result",
    ),
    path(f"{V1}news/", views.NewsView.as_view(), name="partner-news"),
    path(f"{V1}documents/", views.DocumentsView.as_view(), name="partner-documents"),
]

api_patterns = [
    path(f"{V1}openapi.json", openapi.OpenApiView.as_view(), name="partner-openapi"),
    *v1_patterns,
]

# Verwaltung in HUBIplan, unter /api/orgs/<org_id>/
org_patterns = [
    path("api-accesses/", manage_views.ApiAccessListView.as_view(), name="api-accesses"),
    path("api-accesses/<int:pk>/", manage_views.ApiAccessDetailView.as_view(), name="api-access"),
    path(
        "api-accesses/<int:pk>/rotate/",
        manage_views.ApiAccessRotateView.as_view(),
        name="api-access-rotate",
    ),
    path(
        "api-accesses/<int:pk>/resume/",
        manage_views.ApiAccessResumeView.as_view(),
        name="api-access-resume",
    ),
]
