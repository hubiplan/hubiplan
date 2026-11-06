"""Erscheinungsbild je Adresse (White Label W7, konzepte/white-label.md Abschnitt 11).

Eine Instanz kann unter mehreren Adressen laufen. Ist eine Adresse einer Einheit
zugeordnet, zeigen Anmeldeseite, Browser-Tab und Handy-Symbol Name, Farben, Wappen und
Symbol dieser Einheit (mit Vererbung nach oben). Unbekannte Adressen zeigen die Instanz.
Der Host-Header wird nur gegen die Liste ausgewertet, nie in Links übernommen.
"""

from __future__ import annotations

import re

from django.utils.translation import gettext

from .models import InstanceAddress, Organization

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}$")


def normalize_host(host: str) -> str:
    """Hostname ohne Port, klein, ohne Punkt am Ende."""
    host = (host or "").strip().lower()
    if host.startswith("["):  # IPv6 mit Port
        return host
    return host.split(":", 1)[0].rstrip(".")


def clean_hostname(value: str) -> str:
    from django.core.exceptions import ValidationError

    host = normalize_host(value)
    if not HOSTNAME.match(host):
        raise ValidationError(gettext("Bitte eine Adresse wie mitglieder.example.org angeben."))
    return host


def unit_for_host(host: str) -> Organization | None:
    """Einheit, der die aufgerufene Adresse gehört (nur aktive Einheiten)."""
    host = normalize_host(host)
    if not host:
        return None
    address = InstanceAddress.objects.select_related("organization").filter(hostname=host).first()
    if address is None or not address.organization.is_active:
        return None
    return address.organization


def request_unit(request) -> Organization | None:
    try:
        host = request.get_host()
    except Exception:  # noqa: BLE001 – unerlaubter Host: wie unbekannt behandeln
        return None
    return unit_for_host(host)
