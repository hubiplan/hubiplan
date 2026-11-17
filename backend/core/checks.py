"""Systemprüfungen für den Betrieb (``manage.py check --deploy``)."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def proxy_liste(app_configs=None, **kwargs):
    """Gesamtaudit 15.11., OPS-09: Ohne HUBIPLAN_PROXY_HOSTS zählt im Betrieb die Adresse der
    Verbindung, hinter einem Proxy also für alle Besucher dieselbe."""
    if settings.DEBUG or settings.TRUSTED_PROXY_HOSTS or settings.PROXY_TRUST_ALL:
        return []
    return [
        Warning(
            "HUBIPLAN_PROXY_HOSTS ist leer: X-Forwarded-For wird nicht ausgewertet.",
            hint="Hinter einem Proxy dessen Namen oder Adresse eintragen (docs/betrieb.md), "
            "sonst gelten die Grenzen je Adresse für alle Besucher gemeinsam.",
            id="hubiplan.W001",
        )
    ]
