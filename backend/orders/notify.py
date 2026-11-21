"""Push an die Apps, wenn eine Sammelbestellung mit „Push senden“ freigegeben wird. Keine Mail."""

from __future__ import annotations

import logging

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text, language_of_org
from core.tenancy import rls_bypass

from . import services
from .models import OrderCampaign

logger = logging.getLogger(__name__)


def push_data(campaign: OrderCampaign) -> dict:
    return {
        "v": 1,
        "t": "order",
        "id": campaign.pk,
        "title": _("Bestellung: {title}").format(title=campaign.title)[:200],
        "from": services.owner(campaign)[:200],
        "text": _("Bestellen bis {date}").format(date=date_text(campaign.deadline)),
    }


def send(campaign_id: int) -> int:
    from devices.push import app_accesses, send_to_user
    from portal.models import PortalAccess

    with rls_bypass():
        campaign = (
            OrderCampaign.objects.select_related("organization", "department")
            .filter(pk=campaign_id, push=True, pushed_at__isnull=True, published_at__isnull=False)
            .first()
        )
        if campaign is None:
            return 0
        if not OrderCampaign.objects.filter(pk=campaign.pk, pushed_at__isnull=True).update(
            pushed_at=timezone.now()
        ):
            return 0
        members = list(services.audience(campaign).order_by().values_list("pk", flat=True))
        accesses = app_accesses(members)
        users = dict(
            PortalAccess.objects.filter(pk__in=accesses.values()).values_list("pk", "user_id")
        )
        with language_of_org(campaign.organization):
            base = push_data(campaign)
    sent = 0
    for access_id in accesses.values():
        user_id = users.get(access_id)
        if user_id and send_to_user(user_id, {**base, "access": access_id}) > 0:
            sent += 1
    logger.info("Bestellung %s: %s Push", campaign_id, sent)
    return sent
