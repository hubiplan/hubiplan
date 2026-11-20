"""Push an die Apps, wenn ein Beitrag mit „Push senden“ angelegt wurde. Keine Mail."""

from __future__ import annotations

import logging

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import language_of_org
from core.tenancy import rls_bypass

from . import services
from .models import Notice

logger = logging.getLogger(__name__)


def push_data(notice: Notice) -> dict:
    text = " ".join(notice.text.split())
    if len(text) > 140:
        text = text[:139].rstrip() + "…"
    return {
        "v": 1,
        "t": "pinboard",
        "id": notice.pk,
        "title": _("Pinnwand: {owner}").format(owner=services.owner(notice))[:200],
        "from": services.owner(notice)[:200],
        "text": text,
    }


def send(notice_id: int) -> int:
    from devices.push import app_accesses, send_to_user
    from portal.models import PortalAccess

    with rls_bypass():
        notice = (
            Notice.objects.select_related("organization", "department")
            .filter(pk=notice_id, push=True, pushed_at__isnull=True)
            .first()
        )
        if notice is None:
            return 0
        # Nur einmal, auch wenn die Aufgabe doppelt läuft
        if not Notice.objects.filter(pk=notice.pk, pushed_at__isnull=True).update(
            pushed_at=timezone.now()
        ):
            return 0
        accesses = app_accesses(services.recipients(notice))
        users = dict(
            PortalAccess.objects.filter(pk__in=accesses.values()).values_list("pk", "user_id")
        )
        with language_of_org(notice.organization):
            base = push_data(notice)
    sent = 0
    for access_id in accesses.values():
        user_id = users.get(access_id)
        if user_id and send_to_user(user_id, {**base, "access": access_id}) > 0:
            sent += 1
    logger.info("Pinnwand %s: %s Push", notice_id, sent)
    return sent
