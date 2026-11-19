"""Zeitraum einer Buchung als Text (deutsche Zeit), etwa für Rechnungsposten."""

import datetime

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text

from .services import BERLIN


def span_text(booking) -> str:
    start = timezone.localtime(booking.starts_at, BERLIN)
    end = timezone.localtime(booking.ends_at, BERLIN)
    if booking.all_day:
        last = (end - datetime.timedelta(days=1)).date()
        if last <= start.date():
            return _("{date}, ganztägig").format(date=date_text(start.date()))
        return f"{date_text(start.date())} – {date_text(last)}"
    if start.date() == end.date():
        return f"{date_text(start.date())}, {start:%H:%M}–{end:%H:%M}"
    return f"{date_text(start.date())} {start:%H:%M} – {date_text(end.date())} {end:%H:%M}"
