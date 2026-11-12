from django.urls import path

from . import public_views, views

# unter /api/orgs/<org_id>/
org_patterns = [
    path("admission/form/", views.FormSettingsView.as_view(), name="admission-form"),
    path("admission/qr/", views.QrView.as_view(), name="admission-qr"),
    path("admission/", views.ApplicationListView.as_view(), name="admission-list"),
    path("admission/bulk-accept/", views.BulkAcceptView.as_view(), name="admission-bulk"),
    path("admission/kiosk/", views.KioskListView.as_view(), name="admission-kiosk"),
    path("admission/kiosk/<int:pk>/", views.KioskDetailView.as_view(), name="admission-kiosk-link"),
    path("admission/<int:pk>/", views.ApplicationDetailView.as_view(), name="admission-detail"),
    path("admission/<int:pk>/pdf/", views.PdfView.as_view(), name="admission-pdf"),
    path("admission/<int:pk>/<str:action>/", views.ActionView.as_view(), name="admission-action"),
]

# unter /api/
public_patterns = [
    path(
        "public/join/application/<str:token>/",
        public_views.ApplicationStatusView.as_view(),
        name="join-status",
    ),
    path(
        "public/join/application/<str:token>/confirm/",
        public_views.ConfirmView.as_view(),
        name="join-confirm",
    ),
    path(
        "public/join/application/<str:token>/withdraw/",
        public_views.WithdrawView.as_view(),
        name="join-withdraw",
    ),
    path(
        "public/join/application/<str:token>/sign/",
        public_views.SignView.as_view(),
        name="join-sign",
    ),
    path(
        "public/join/application/<str:token>/pdf/",
        public_views.PdfView.as_view(),
        name="join-pdf",
    ),
    path("public/join/kiosk/<str:token>/", public_views.KioskView.as_view(), name="join-kiosk"),
    path("public/join/<str:key>/", public_views.FormView.as_view(), name="join-form"),
]
