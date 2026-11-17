"""Pfade der Beitragsnachweise: Verein, Mitgliederbereich und persönlicher Link."""

from django.urls import path

from . import views

org_patterns = [
    path("fee-proofs/", views.ProofListView.as_view()),
    path("fee-proofs/settings/", views.SettingsView.as_view()),
    path("fee-proofs/overview/", views.OverviewView.as_view()),
    path("fee-proofs/<int:pk>/", views.ProofDetailView.as_view()),
    path("fee-proofs/<int:pk>/<str:action>/", views.ProofDetailView.as_view()),
    path("members/<int:member_pk>/fee-proofs/", views.MemberProofsView.as_view()),
]

portal_patterns = [
    path("fee-proofs/", views.PortalProofsView.as_view()),
]

public_patterns = [
    path("public/fee-proof/<str:token>/", views.PublicLinkView.as_view(), name="public-fee-proof"),
]
