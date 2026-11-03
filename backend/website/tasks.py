"""Hintergrund-Jobs der Webseite."""

from celery import shared_task

from .contact import purge_held


@shared_task
def purge_held_messages() -> int:
    """Täglich: zurückgehaltene Formularnachrichten nach 7 Tagen löschen."""
    return purge_held()


@shared_task
def sync_social_feed(feed_id: int, token: str) -> int:
    """Manual fetch: tenant is determined from the stored feed, never client input."""
    from core.tenancy import rls_bypass, tenant_context

    from .social import sync_feed
    from .social_models import SocialFeed

    try:
        with rls_bypass():
            feed = SocialFeed.objects.filter(pk=feed_id, sync_job_id=token).first()
        if feed is None:
            return 0
        with tenant_context(feed.organization_id):
            return sync_feed(feed)
    finally:
        with rls_bypass():
            SocialFeed.objects.filter(pk=feed_id, sync_job_id=token).update(
                sync_job_id=None, sync_requested_at=None
            )


@shared_task
def sync_social_feeds() -> int:
    """Alle 30 Minuten: dieselben deduplizierten Aufträge wie beim manuellen Abruf."""
    from core.tenancy import rls_bypass

    from .social_jobs import request_sync
    from .social_models import SocialFeed

    with rls_bypass():
        return sum(
            request_sync(feed)
            for feed in SocialFeed.objects.filter(is_active=True).exclude(access_token="")
            if feed.is_connected
        )


@shared_task
def maintain_social_feeds() -> None:
    """Täglich: Instagram-Zugänge verlängern, Facebook-Zugänge prüfen."""
    from core.tenancy import rls_bypass

    from .social import maintain_all

    with rls_bypass():
        maintain_all()
