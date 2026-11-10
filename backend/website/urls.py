"""Adressen der Webseite (eingebunden in core/urls.py)."""

from django.urls import path

from . import (
    content_views,
    design_views,
    document_views,
    gallery_views,
    public_views,
    social_views,
    views,
)

org_patterns = [
    path("chronicle/", content_views.ChronicleView.as_view(), name="chronicle"),
    path("website/", views.WebsiteView.as_view(), name="website"),
    path(
        "website/privacy/generate/",
        views.PrivacyGenerateView.as_view(),
        name="website-privacy-generate",
    ),
    path(
        "website/privacy/publish/",
        views.PrivacyPublishView.as_view(),
        name="website-privacy-publish",
    ),
    path(
        "website/design-packages/",
        design_views.DesignPackageListView.as_view(),
        name="website-design-packages",
    ),
    path(
        "website/design-packages/<slug:key>/",
        design_views.DesignPackageDetailView.as_view(),
        name="website-design-package",
    ),
    path(
        "website/design-packages/<slug:key>/export/",
        design_views.DesignPackageExportView.as_view(),
        name="website-design-package-export",
    ),
    path("website/domains/", views.DomainListView.as_view(), name="website-domains"),
    path("website/domains/<int:pk>/", views.DomainDetailView.as_view(), name="website-domain"),
    path(
        "website/preview-links/",
        views.PreviewLinkListView.as_view(),
        name="website-preview-links",
    ),
    path(
        "website/preview-links/<int:pk>/",
        views.PreviewLinkDetailView.as_view(),
        name="website-preview-link",
    ),
    path("website/preview/", views.PreviewOpenView.as_view(), name="website-preview"),
    path(
        "website/design/publish/", views.DesignPublishView.as_view(), name="website-design-publish"
    ),
    path("website/home-content/", views.HomeContentView.as_view(), name="website-home-content"),
    path(
        "website/home-content/publish/",
        views.HomeContentPublishView.as_view(),
        name="website-home-content-publish",
    ),
    path(
        "website/design/discard/", views.DesignDiscardView.as_view(), name="website-design-discard"
    ),
    path(
        "website/design/versions/<int:pk>/restore/",
        views.DesignRestoreView.as_view(),
        name="website-design-restore",
    ),
    path("website/held/", views.HeldListView.as_view(), name="website-held"),
    path("website/held/<int:pk>/", views.HeldDetailView.as_view(), name="website-held-message"),
    path("website/texts/", content_views.TextListView.as_view(), name="website-texts"),
    path(
        "website/texts/reorder/",
        content_views.PageOrderView.as_view(),
        name="website-texts-reorder",
    ),
    path("website/texts/<int:pk>/", content_views.TextDetailView.as_view(), name="website-text"),
    path(
        "website/texts/<int:pk>/publish/",
        content_views.TextPublishView.as_view(),
        name="website-text-publish",
    ),
    path(
        "website/texts/<int:pk>/revisions/<int:rev>/restore/",
        content_views.TextRestoreView.as_view(),
        name="website-text-restore",
    ),
    path(
        "website/texts/<int:pk>/timeline-import/",
        content_views.TimelineImportView.as_view(),
        name="website-text-timeline-import",
    ),
    path("website/images/", content_views.ImageListView.as_view(), name="website-images"),
    path("website/images/<int:pk>/", content_views.ImageDetailView.as_view(), name="website-image"),
    path(
        "website/images/<int:pk>/crop/",
        content_views.ImageCropView.as_view(),
        name="website-image-crop",
    ),
    path(
        "website/images/<int:pk>/replace/",
        content_views.ImageReplaceView.as_view(),
        name="website-image-replace",
    ),
    path(
        "website/images/<int:pk>/copy/",
        content_views.ImageCopyView.as_view(),
        name="website-image-copy",
    ),
    path(
        "website/images/<int:pk>/file/",
        content_views.ImageFileView.as_view(),
        name="website-image-file",
    ),
    path("website/documents/", document_views.DocumentListView.as_view(), name="website-documents"),
    path(
        "website/documents/<int:pk>/",
        document_views.DocumentDetailView.as_view(),
        name="website-document",
    ),
    path(
        "website/documents/<int:pk>/file/",
        document_views.DocumentFileView.as_view(),
        name="website-document-file",
    ),
    path("website/albums/", gallery_views.AlbumListView.as_view(), name="website-albums"),
    path(
        "website/albums/reorder/",
        gallery_views.AlbumOrderView.as_view(),
        name="website-albums-reorder",
    ),
    path("website/albums/<int:pk>/", gallery_views.AlbumDetailView.as_view(), name="website-album"),
    path(
        "website/albums/<int:pk>/images/",
        gallery_views.AlbumImagesView.as_view(),
        name="website-album-images",
    ),
    path("website/social/", social_views.FeedListView.as_view(), name="website-social"),
    path(
        "website/social/<int:pk>/",
        social_views.FeedDetailView.as_view(),
        name="website-social-feed",
    ),
    path(
        "website/social/<int:pk>/connect/",
        social_views.FeedConnectView.as_view(),
        name="website-social-connect",
    ),
    path(
        "website/social/<int:pk>/page/",
        social_views.FeedPageView.as_view(),
        name="website-social-page",
    ),
    path(
        "website/social/<int:pk>/publish-pending/",
        social_views.FeedPublishPendingView.as_view(),
        name="website-social-publish-pending",
    ),
    path(
        "website/social/<int:pk>/sync/",
        social_views.FeedSyncView.as_view(),
        name="website-social-sync",
    ),
    path("website/social/posts/", social_views.PostListView.as_view(), name="website-social-posts"),
    path(
        "website/social/posts/<int:pk>/",
        social_views.PostDetailView.as_view(),
        name="website-social-post",
    ),
    path(
        "website/social/images/<int:pk>/file/",
        social_views.PostImageFileView.as_view(),
        name="website-social-image",
    ),
    path(
        "members/<int:pk>/publication/",
        views.MemberPublicationView.as_view(),
        name="member-publication",
    ),
]

SITE = "public/site/v1/<str:key>/"
public_patterns = [
    path(
        "website/social/callback/",
        social_views.CallbackView.as_view(),
        name="website-social-callback",
    ),
    path("public/site/v1/instance/", public_views.InstanceView.as_view(), name="site-instance"),
    path("public/site/v1/resolve/", public_views.ResolveView.as_view(), name="site-resolve"),
    path(SITE, public_views.SiteInfoView.as_view(), name="site-info"),
    path(f"{SITE}preview/", public_views.PreviewView.as_view(), name="site-preview"),
    path(f"{SITE}icon-<str:name>.png", public_views.SiteIconView.as_view(), name="site-icon"),
    path(
        f"{SITE}design/<slug:package>/",
        public_views.DesignPackageView.as_view(),
        name="site-design-package",
    ),
    path(f"{SITE}board/", public_views.BoardView.as_view(), name="site-board"),
    path(f"{SITE}units/", public_views.UnitListView.as_view(), name="site-units"),
    path(f"{SITE}units/<str:slug>/", public_views.UnitDetailView.as_view(), name="site-unit"),
    path(f"{SITE}pages/<str:slug>/", public_views.PageView.as_view(), name="site-page"),
    path(f"{SITE}images/<str:image_key>/", public_views.ImageView.as_view(), name="site-image"),
    path(f"{SITE}galleries/", public_views.GalleryListView.as_view(), name="site-galleries"),
    path(
        f"{SITE}galleries/<slug:slug>/",
        public_views.GalleryDetailView.as_view(),
        name="site-gallery",
    ),
    path(f"{SITE}photos/<str:token>/", public_views.PhotoView.as_view(), name="site-photo"),
    path(f"{SITE}honors/", public_views.HonorsView.as_view(), name="site-honors"),
    path(f"{SITE}members/<str:slug>/", public_views.MembersView.as_view(), name="site-members"),
    path(f"{SITE}memorial/", public_views.MemorialView.as_view(), name="site-memorial"),
    path(f"{SITE}search/", public_views.SearchView.as_view(), name="site-search"),
    path(f"{SITE}repertoire/", public_views.RepertoireView.as_view(), name="site-repertoire"),
    path(f"{SITE}documents/", public_views.DocumentsView.as_view(), name="site-documents"),
    path(
        f"{SITE}files/<str:token>/",
        public_views.DocumentFileView.as_view(),
        name="site-document-file",
    ),
    path(f"{SITE}results/", public_views.ResultsView.as_view(), name="site-results"),
    path(
        f"{SITE}results/series/<str:token>/",
        public_views.ResultSeriesView.as_view(),
        name="site-results-series",
    ),
    path(
        f"{SITE}results/<str:token>/", public_views.ResultDetailView.as_view(), name="site-result"
    ),
    path(
        f"{SITE}results/<str:token>/version/",
        public_views.ResultVersionView.as_view(),
        name="site-result-version",
    ),
    path(
        f"{SITE}honors/photos/<str:token>/",
        public_views.HonorsPhotoView.as_view(),
        name="site-honors-photo",
    ),
    path(f"{SITE}imprint/", public_views.ImprintView.as_view(), name="site-imprint"),
    path(
        f"{SITE}statute/preview/",
        public_views.StatutePreviewView.as_view(),
        name="site-statute-preview",
    ),
    path(
        f"{SITE}fee-rules/preview/",
        public_views.StatutePreviewView.as_view(kind="fee_rules"),
        name="site-fee-rules-preview",
    ),
    path(
        f"{SITE}founding-deed/preview/",
        public_views.StatutePreviewView.as_view(kind="founding_deed"),
        name="site-founding-deed-preview",
    ),
    path(f"{SITE}events/", public_views.EventsView.as_view(), name="site-events"),
    path(f"{SITE}events.ics", public_views.EventsIcsView.as_view(), name="site-events-ics"),
    path(f"{SITE}bookings/", public_views.BookingsView.as_view(), name="site-bookings"),
    path(f"{SITE}bookings.ics", public_views.BookingsIcsView.as_view(), name="site-bookings-ics"),
    path(f"{SITE}posts/", public_views.PostsView.as_view(), name="site-posts"),
    path(
        f"{SITE}posts/images/<str:image_key>/",
        public_views.PostImageView.as_view(),
        name="site-post-image",
    ),
    path(f"{SITE}contact/", public_views.ContactView.as_view(), name="site-contact"),
]
