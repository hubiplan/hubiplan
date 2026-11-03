"""Atomically coalesce manual requests across all web processes."""

import datetime
import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .social_models import SocialFeed


def request_sync(feed):
    from .tasks import sync_social_feed

    token = uuid.uuid4()
    now = timezone.now()
    updated = (
        SocialFeed.objects.filter(pk=feed.pk)
        .filter(
            Q(sync_job_id__isnull=True)
            | Q(sync_requested_at__lt=now - datetime.timedelta(minutes=30))
        )
        .update(sync_job_id=token, sync_requested_at=now)
    )
    if not updated:
        return False

    def enqueue():
        try:
            sync_social_feed.delay(feed.pk, str(token))
        except Exception:
            SocialFeed.objects.filter(pk=feed.pk, sync_job_id=token).update(
                sync_job_id=None, sync_requested_at=None
            )
            raise

    transaction.on_commit(enqueue)
    return True
