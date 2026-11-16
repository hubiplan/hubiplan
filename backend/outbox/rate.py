"""Stundengrenze für alle Massenmails (Gesamtaudit 15.11., PF-09, Fachfrage FF-41).

Bisher hielten nur Rundschreiben ``MAIL_RATE_PER_HOUR`` ein. Termin-Einladungen und
-Erinnerungen an tausende Mitglieder liefen am Postfach-Limit auf und verbrauchten das
Budget der Rundschreiben. Jetzt nehmen auch sie je Mail einen Platz der Stunde; ein Zehntel
bleibt wie bei Rundschreiben für Anmelde- und Sicherheitsmails frei, die nie warten.
Ohne gesetzte Grenze gibt es keine Grenze (wie bisher).
"""

from __future__ import annotations

from django.conf import settings
from django.db import connection, transaction


def take() -> bool:
    """Platz für eine Massenmail in dieser Stunde? Unter derselben Sperre wie Rundschreiben."""
    limit = settings.MAIL_RATE_PER_HOUR
    if not limit:
        return True
    from circulars.services import MAIL_LOCK, _mail_room

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", list(MAIL_LOCK))
        return _mail_room(limit) > 0
