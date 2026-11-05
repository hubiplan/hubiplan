"""Wallet-Abgleich einschließlich Austritt, Tageswechsel und fehlgeschlagener Übertragung."""

import logging

from celery import shared_task

from core.tenancy import rls_bypass

from . import wallet
from .models import MemberCard

logger = logging.getLogger(__name__)


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=1500, time_limit=1560)
def sync_wallets():
    if not wallet.enabled():
        return
    client = wallet.GoogleWallet()
    with rls_bypass():
        ids = MemberCard.objects.exclude(wallet_passes={}).values_list("pk", flat=True)
        for card_id in ids.iterator():
            try:
                wallet.sync_google(card_id, client)
            except wallet.WalletError:
                # Keine Anbieterantworten oder personenbezogenen Passinhalte protokollieren.
                logger.warning("Wallet-Abgleich für Ausweis %s fehlgeschlagen", card_id)
