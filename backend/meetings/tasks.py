"""Hintergrundjobs der Versammlungen."""

from __future__ import annotations

from celery import shared_task


@shared_task
def mix_secret_polls() -> int:
    """Stimmzettel offener geheimer Abstimmungen mischen (Gesamtaudit 15.11., GEH-1)."""
    from . import live

    return live.mix_open_polls()
